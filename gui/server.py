"""gui/server.py — веб-сервер GUI. Запуск: python server.py → http://localhost:8765"""
from __future__ import annotations
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Collection, Environment, Request
from core.variables import Env
from core.executor import execute, run_collection, summarize
from core.storage import (
    gen_id, save_collection, load_collection, list_collections, delete_collection,
    save_environment, list_environments, delete_environment,
    append_history, get_history, clear_history, load_settings, save_settings,
)

HOST, PORT = "127.0.0.1", 8765


def _seed_demo():
    """Создать демо-данные при первом запуске."""
    if list_collections():
        return
    col = Collection(
        id="demo01", name="JSONPlaceholder Demo",
        description="Демо-коллекция для публичного REST API",
        variables={"BASE_URL": "https://jsonplaceholder.typicode.com"},
    )
    from core.models import Folder
    posts = Folder(id="f01", name="Posts", requests=[
        Request(id="r01", name="Получить список постов",
                method="GET", url="{{BASE_URL}}/posts",
                headers={"Accept": "application/json"},
                params={"_limit": "5"},
                test_script=(
                    "pm.test('Статус 200', lambda: pm.expect(pm.response.status).to.equal(200))\n"
                    "pm.test('Массив данных', lambda: pm.expect(pm.response.json()).to.a('array'))\n"
                    "pm.test('Быстрый ответ', lambda: pm.expect(pm.response.time).to.below(5000))"
                )),
        Request(id="r02", name="Получить пост по ID",
                method="GET", url="{{BASE_URL}}/posts/1",
                test_script=(
                    "pm.test('Статус 200', lambda: pm.expect(pm.response.status).to.equal(200))\n"
                    "pm.test('ID равен 1', lambda: pm.expect(pm.response.json()['id']).to.equal(1))\n"
                    "pm.environment.set('last_post_id', str(pm.response.json()['id']))"
                )),
        Request(id="r03", name="Создать пост",
                method="POST", url="{{BASE_URL}}/posts",
                headers={"Content-Type": "application/json"},
                body_format="json",
                body='{\n  "title": "API Sentinel Test",\n  "body": "Created by test",\n  "userId": 1\n}',
                test_script=(
                    "pm.test('Статус 201', lambda: pm.expect(pm.response.status).to.equal(201))\n"
                    "pm.test('Ответ — объект', lambda: pm.expect(pm.response.json()).to.a('object'))"
                )),
    ])
    users = Folder(id="f02", name="Users", requests=[
        Request(id="r04", name="Список пользователей",
                method="GET", url="{{BASE_URL}}/users",
                test_script=(
                    "pm.test('Статус 200', lambda: pm.expect(pm.response.status).to.equal(200))\n"
                    "pm.test('10 пользователей', lambda: pm.expect(len(pm.response.json())).to.equal(10))"
                )),
    ])
    col.folders = [posts, users]
    save_collection(col)
    save_environment(Environment(id="env01", name="Production",
        variables={"BASE_URL": "https://jsonplaceholder.typicode.com", "TOKEN": "prod-token"}))
    save_environment(Environment(id="env02", name="Staging",
        variables={"BASE_URL": "https://jsonplaceholder.typicode.com", "TOKEN": "staging-token"}))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        qs = parse_qs(parsed.query)

        if p in ("/", "/index.html"):
            self._file(ROOT / "gui" / "index.html", "text/html"); return

        if not p.startswith("/api/"):
            self.send_response(404); self.end_headers(); return

        if p == "/api/collections":
            return self._json({"collections": [c.to_dict() for c in list_collections()]})
        if p.startswith("/api/collections/"):
            cid = p.split("/")[-1]
            col = load_collection(cid)
            return self._json(col.to_dict() if col else {"error": "not found"}, 200 if col else 404)
        if p == "/api/environments":
            return self._json({"environments": [e.to_dict() for e in list_environments()]})
        if p == "/api/history":
            limit = int(qs.get("limit", ["50"])[0])
            return self._json({"history": get_history(limit)})
        if p == "/api/settings":
            return self._json(load_settings())
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._body()
        p = urlparse(self.path).path

        if p == "/api/execute":
            return self._json(self._handle_execute(body))
        if p == "/api/run":
            return self._json(self._handle_run(body))
        if p == "/api/collections":
            if not body.get("id"): body["id"] = gen_id()
            col = Collection.from_dict(body)
            save_collection(col)
            return self._json({"ok": True, "id": col.id})
        if p == "/api/environments":
            if not body.get("id"): body["id"] = gen_id()
            env = Environment.from_dict(body)
            save_environment(env)
            return self._json({"ok": True, "id": env.id})
        if p == "/api/settings":
            save_settings(body); return self._json({"ok": True})
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/api/collections/"):
            return self._json({"ok": delete_collection(p.split("/")[-1])})
        if p.startswith("/api/environments/"):
            return self._json({"ok": delete_environment(p.split("/")[-1])})
        if p == "/api/history":
            clear_history(); return self._json({"ok": True})
        self._json({"error": "not found"}, 404)

    def _handle_execute(self, body: dict) -> dict:
        try:
            settings = load_settings()
            env_vars = dict(body.get("env_vars") or {})
            if body.get("environment_id"):
                for e in list_environments():
                    if e.id == body["environment_id"]:
                        env_vars = {**e.variables, **env_vars}
                        break
            env = Env(env_vars=env_vars)
            req = Request(
                id=body.get("id") or gen_id(),
                name=body.get("name") or f"{body.get('method','GET')} {body.get('url','')}",
                method=body.get("method", "GET"),
                url=body.get("url", ""),
                headers=body.get("headers") or {},
                params=body.get("params") or {},
                body_format=body.get("body_format", "none"),
                body=body.get("body"),
                pre_script=body.get("pre_script"),
                test_script=body.get("test_script"),
            )
            result = execute(req, env,
                             verify_ssl=settings["verify_ssl"],
                             timeout=settings["timeout"])
            append_history({
                "request_name": req.name, "method": req.method, "url": req.url,
                "response": result.response.to_dict() if result.response else None,
                "assertions": [a.to_dict() for a in result.assertions],
                "passed": result.passed, "error": result.error,
            })
            return result.to_dict()
        except Exception as e:
            return {"error": str(e)}

    def _handle_run(self, body: dict) -> dict:
        try:
            col = load_collection(body.get("collection_id", ""))
            if not col: return {"error": "Коллекция не найдена"}
            env_vars = dict(col.variables)
            if body.get("environment_id"):
                for e in list_environments():
                    if e.id == body["environment_id"]:
                        env_vars.update(e.variables)
                        break
            env = Env(env_vars=env_vars)
            requests = col.all_requests()
            settings = load_settings()
            results  = run_collection(requests, env,
                                      verify_ssl=settings["verify_ssl"],
                                      timeout=settings["timeout"])
            s = summarize(results)
            return {"results": [r.to_dict() for r in results], "summary": s}
        except Exception as e:
            return {"error": str(e)}

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try: return json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception: return {}
        return {}

    def _json(self, data: dict, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._cors(); self.end_headers()
        self.wfile.write(payload)

    def _file(self, path: Path, ct: str):
        if not path.exists():
            self.send_response(404); self.end_headers(); return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self._cors(); self.end_headers()
        self.wfile.write(data)


def run():
    _seed_demo()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"\n  ╔════════════════════════════════════════╗")
    print(f"  ║        API  S E N T I N E L          ║")
    print(f"  ║  HTTP-клиент для тестирования API     ║")
    print(f"  ╚════════════════════════════════════════╝")
    print(f"\n  ● Сервер запущен: http://{HOST}:{PORT}")
    print(f"  ● Откройте браузер по этому адресу")
    print(f"  ● Ctrl+C для остановки\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Сервер остановлен.")


if __name__ == "__main__":
    run()
