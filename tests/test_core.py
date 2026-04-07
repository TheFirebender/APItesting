"""tests/test_core.py — модульные тесты ядра (НФТ-4.3). Запуск: python -m pytest -v"""
import sys, os, json, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.variables import Env
from core.scripts   import run_pre, run_test
from core.models    import Response, Request, Assertion, Result, Collection
from core.reporter  import to_junit, to_json, to_text


# ── VariableEnvironment ────────────────────────────────────────────────────────
class TestEnv(unittest.TestCase):

    def mk(self): return Env(global_vars={"APP":"Sentinel","VER":"1.0"},
                              env_vars={"BASE":"https://api.test.com","TOK":"secret"})

    def test_resolve_simple(self):
        self.assertEqual(self.mk().resolve("{{BASE}}/users"), "https://api.test.com/users")

    def test_resolve_multiple(self):
        self.assertEqual(self.mk().resolve("{{APP}} v{{VER}}"), "Sentinel v1.0")

    def test_unknown_stays(self):
        self.assertEqual(self.mk().resolve("{{NOPE}}"), "{{NOPE}}")

    def test_priority_local_over_env(self):
        e = self.mk(); e.set("TOK","local","local")
        self.assertEqual(e.get("TOK"), "local")

    def test_priority_env_over_global(self):
        e = Env(global_vars={"X":"global"}, env_vars={"X":"env"})
        self.assertEqual(e.get("X"), "env")

    def test_resolve_dict(self):
        r = self.mk().resolve_dict({"Auth":"Bearer {{TOK}}","X-App":"{{APP}}"})
        self.assertEqual(r["Auth"], "Bearer secret")
        self.assertEqual(r["X-App"], "Sentinel")

    def test_clone_independence(self):
        e = self.mk(); cl = e.clone()
        cl.set("BASE","https://staging.test.com")
        self.assertEqual(e.get("BASE"), "https://api.test.com")

    def test_resolve_none(self):
        self.assertEqual(self.mk().resolve(None), "")

    def test_resolve_empty(self):
        self.assertEqual(self.mk().resolve(""), "")

    def test_snapshot(self):
        snap = self.mk().snapshot()
        self.assertIn("BASE", snap); self.assertIn("APP", snap)

    def test_set_and_get(self):
        e = Env(); e.set("K","V")
        self.assertEqual(e.get("K"), "V")


# ── Scripts ────────────────────────────────────────────────────────────────────
def _resp(code=200, body='{"id":1,"name":"test"}', ms=120.0):
    return Response(code, "OK", {"content-type":"application/json"},
                    body, ms, len(body), "https://t.com", "GET")

class TestScripts(unittest.TestCase):

    def test_assertion_pass(self):
        env = Env()
        assertions, err = run_test(
            "pm.test('Status 200', lambda: pm.expect(pm.response.status).to.equal(200))",
            env, _resp(200))
        self.assertIsNone(err)
        self.assertEqual(len(assertions), 1)
        self.assertTrue(assertions[0].passed)

    def test_assertion_fail(self):
        env = Env()
        assertions, _ = run_test(
            "pm.test('Status 201', lambda: pm.expect(pm.response.status).to.equal(201))",
            env, _resp(200))
        self.assertFalse(assertions[0].passed)
        self.assertIn("201", assertions[0].message)

    def test_multiple_assertions(self):
        env = Env()
        script = "\n".join([
            "pm.test('Status 200', lambda: pm.expect(pm.response.status).to.equal(200))",
            "pm.test('Fast', lambda: pm.expect(pm.response.time).to.below(1000))",
            "pm.test('JSON', lambda: pm.expect(pm.response.json()).to.a('object'))",
        ])
        assertions, _ = run_test(script, env, _resp())
        self.assertEqual(len(assertions), 3)
        self.assertTrue(all(a.passed for a in assertions))

    def test_extract_var(self):
        env = Env()
        run_test(
            "d = pm.response.json()\npm.environment.set('got_id', str(d['id']))",
            env, _resp(200, '{"id":42}'))
        self.assertEqual(env.get("got_id"), "42")

    def test_pre_set_var(self):
        env = Env(); hdrs = {}
        err = run_pre("pm.environment.set('token','Bearer xyz')", env, hdrs)
        self.assertIsNone(err)
        self.assertEqual(env.get("token"), "Bearer xyz")

    def test_pre_modify_headers(self):
        env = Env(); hdrs = {"Content-Type":"application/json"}
        run_pre("pm.headers['X-Custom'] = 'test'", env, hdrs)
        self.assertEqual(hdrs["X-Custom"], "test")

    def test_syntax_error(self):
        env = Env()
        _, err = run_test("def broken(", env, _resp())
        self.assertIsNotNone(err)

    def test_empty_script(self):
        env = Env(); hdrs = {}
        self.assertIsNone(run_pre("", env, hdrs))
        self.assertIsNone(run_pre(None, env, hdrs))

    def test_expect_above_below(self):
        env = Env()
        assertions, _ = run_test("\n".join([
            "pm.test('above 0',   lambda: pm.expect(pm.response.status).to.above(0))",
            "pm.test('below 300', lambda: pm.expect(pm.response.status).to.below(300))",
        ]), env, _resp(200))
        self.assertTrue(all(a.passed for a in assertions))

    def test_expect_include(self):
        env = Env()
        assertions, _ = run_test(
            "pm.test('body has id', lambda: pm.expect(pm.response.body).to.include('id'))",
            env, _resp())
        self.assertTrue(assertions[0].passed)

    def test_not_equal(self):
        env = Env()
        assertions, _ = run_test(
            "pm.test('not 500', lambda: pm.expect(pm.response.status).not_.equal(500))",
            env, _resp(200))
        self.assertTrue(assertions[0].passed)


# ── Models ─────────────────────────────────────────────────────────────────────
class TestModels(unittest.TestCase):

    def test_request_roundtrip(self):
        r = Request(id="r1", name="Test", method="POST", url="https://api.test.com/users")
        d = r.to_dict()
        r2 = Request.from_dict(d)
        self.assertEqual(r2.method, "POST"); self.assertEqual(r2.url, r.url)

    def test_collection_all_requests(self):
        from core.models import Folder
        col = Collection(id="c1", name="Test",
                         requests=[Request(id="r1",name="Root")],
                         folders=[Folder(id="f1",name="F",requests=[Request(id="r2",name="Folder")])])
        all_r = col.all_requests()
        self.assertEqual(len(all_r), 2)
        self.assertEqual({r.id for r in all_r}, {"r1","r2"})

    def test_response_color(self):
        def resp(c): return Response(c,"X",{},"",.0,0,"","GET")
        self.assertEqual(resp(200).color, "green")
        self.assertEqual(resp(301).color, "blue")
        self.assertEqual(resp(404).color, "yellow")
        self.assertEqual(resp(500).color, "red")

    def test_response_is_json(self):
        r = Response(200,"OK",{"content-type":"application/json"},'{"a":1}',.0,0,"","GET")
        self.assertTrue(r.is_json)

    def test_result_passed(self):
        resp = Response(200,"OK",{},"{}",.0,0,"","GET")
        res  = Result("r1","T","GET","url",resp,
                      assertions=[Assertion("A",True),Assertion("B",True)])
        self.assertTrue(res.passed)

    def test_result_failed_assertion(self):
        resp = Response(200,"OK",{},"{}",.0,0,"","GET")
        res  = Result("r1","T","GET","url",resp,
                      assertions=[Assertion("A",True),Assertion("B",False,"fail")])
        self.assertFalse(res.passed)

    def test_result_failed_error(self):
        res = Result("r1","T","GET","url",None,error="Connection refused")
        self.assertFalse(res.passed)


# ── Reporter ───────────────────────────────────────────────────────────────────
def _result(name="Test", passed=True, code=200):
    resp = Response(code,"OK",{},"{}", 100.0, 2, "url","GET")
    return Result("r1", name, "GET", "url", resp,
                  assertions=[Assertion("Check", passed, None if passed else "fail")])

_SUM = {"total":2,"passed":1,"failed":1,"total_assertions":2,
        "passed_assertions":1,"avg_ms":100,"success_rate":50}

class TestReporter(unittest.TestCase):

    def test_junit_structure(self):
        xml = to_junit([_result("A"), _result("B", False)])
        self.assertIn("<testsuite", xml)
        self.assertIn('name="A"', xml)
        self.assertIn("<failure", xml)

    def test_json_valid(self):
        s = to_json([_result("T1"),_result("T2")], _SUM)
        obj = json.loads(s)
        self.assertEqual(obj["summary"]["total"], 2)
        self.assertIsInstance(obj["results"], list)

    def test_text_contains_pass(self):
        txt = to_text([_result("GET /users")], _SUM)
        self.assertIn("GET /users", txt); self.assertIn("✓", txt)


# ── Executor unit (no network) ────────────────────────────────────────────────
class TestExecutorUnit(unittest.TestCase):

    def test_bad_url_returns_error(self):
        from core.executor import execute
        req = Request(id="t1",name="Bad",method="GET",url="http://256.256.256.256/x")
        res = execute(req, Env(), timeout=1)
        self.assertIsNotNone(res.error)

    def test_unreachable_host(self):
        from core.executor import execute
        req = Request(id="t2",name="Dead",method="GET",url="http://127.0.0.1:19999/x")
        res = execute(req, Env(), timeout=1)
        self.assertIsNotNone(res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
