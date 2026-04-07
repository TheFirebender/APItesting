"""core/executor.py — HTTP-ядро: переменные → pre → HTTP → test → метрики."""
from __future__ import annotations
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

from .models import Request, Response, Result, Assertion
from .variables import Env
from .scripts import run_pre, run_test


def execute(req: Request, env: Env,
            verify_ssl: bool = True,
            timeout: int = 30) -> Result:
    local = env.clone()

    # 1. Resolve variables
    url     = local.resolve(req.url)
    headers = local.resolve_dict(req.headers)
    params  = local.resolve_dict(req.params)
    body    = local.resolve(req.body) if req.body else None

    # 2. Pre-request script
    pre_err = None
    if req.pre_script:
        pre_err = run_pre(req.pre_script, local, headers)

    # 3. Build URL with query params
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)

    # 4. HTTP
    resp, http_err = _send(req.method, url, headers, body, req.body_format,
                           verify_ssl=verify_ssl, timeout=timeout)
    if http_err:
        return Result(req.id, req.name, req.method, url,
                      response=None, error=http_err, pre_error=pre_err)

    # 5. Test script
    assertions: List[Assertion] = []
    test_err = None
    if req.test_script and resp:
        assertions, test_err = run_test(req.test_script, local, resp)
        # sync env
        for k, v in local.snapshot().items():
            if env.get(k) != v:
                env.set(k, v)

    return Result(req.id, req.name, req.method, url,
                  response=resp, assertions=assertions,
                  pre_error=pre_err, test_error=test_err)


def _send(method: str, url: str, headers: dict,
          body: Optional[str], fmt: str,
          verify_ssl: bool, timeout: int) -> Tuple[Optional[Response], Optional[str]]:
    # Content-Type
    encoded = None
    if body:
        ct_map = {"json": "application/json", "xml": "application/xml",
                  "form": "application/x-www-form-urlencoded", "text": "text/plain"}
        if fmt in ct_map and "content-type" not in {k.lower() for k in headers}:
            headers["Content-Type"] = ct_map[fmt]
        encoded = body.encode("utf-8")

    ssl_ctx = ssl.create_default_context()
    if not verify_ssl:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode    = ssl.CERT_NONE

    r = urllib.request.Request(url=url, data=encoded,
                               method=method.upper(), headers=headers)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=ssl_ctx) as resp:
            raw  = resp.read()
            ms   = (time.perf_counter() - t0) * 1000
            body_str = _decode(raw, resp.headers.get("Content-Type", ""))
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return Response(resp.status, resp.reason or "", hdrs,
                            body_str, round(ms, 1), len(raw), url, method.upper()), None
    except urllib.error.HTTPError as e:
        raw  = e.read()
        ms   = (time.perf_counter() - t0) * 1000
        body_str = _decode(raw, e.headers.get("Content-Type", ""))
        hdrs = {k.lower(): v for k, v in e.headers.items()}
        return Response(e.code, e.reason or "", hdrs,
                        body_str, round(ms, 1), len(raw), url, method.upper()), None
    except urllib.error.URLError as e:
        return None, f"Ошибка соединения: {e.reason}"
    except TimeoutError:
        return None, f"Таймаут ({timeout}с)"
    except Exception as e:
        return None, str(e)


def _decode(raw: bytes, ct: str) -> str:
    charset = "utf-8"
    if "charset=" in ct:
        try: charset = ct.split("charset=")[-1].strip().split(";")[0]
        except Exception: pass
    try:   return raw.decode(charset, errors="replace")
    except LookupError: return raw.decode("utf-8", errors="replace")


def run_collection(requests: list, env: Env,
                   verify_ssl=True, timeout=30,
                   on_result=None) -> list:
    results = []
    for req in requests:
        r = execute(req, env, verify_ssl=verify_ssl, timeout=timeout)
        results.append(r)
        if on_result:
            on_result(r)
    return results


def summarize(results: list) -> dict:
    total  = len(results)
    passed = sum(1 for r in results if r.passed)
    times  = [r.response.elapsed_ms for r in results if r.response]
    total_ass  = sum(len(r.assertions) for r in results)
    passed_ass = sum(sum(1 for a in r.assertions if a.passed) for r in results)
    return {
        "total": total, "passed": passed, "failed": total - passed,
        "total_assertions": total_ass, "passed_assertions": passed_ass,
        "avg_ms": round(sum(times) / len(times), 1) if times else 0,
        "success_rate": round(passed / total * 100, 1) if total else 0,
    }
