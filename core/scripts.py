"""core/scripts.py — движок Pre-request / Test Script."""
from __future__ import annotations
import json
import traceback
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Response, Assertion
    from .variables import Env


# ── Expect chain ───────────────────────────────────────────────────────────────

class Expect:
    def __init__(self, val: Any):
        self._v = val
        self.to = self
        self.be = self

    class _Not:
        def __init__(self, val):
            self._v = val
            self.to = self; self.be = self
        def equal(self, e):
            if self._v == e: raise AssertionError(f"Expected NOT {e!r}")
        def include(self, s):
            if str(s) in str(self._v): raise AssertionError(f"Expected NOT to include {s!r}")

    @property
    def not_(self):
        return self._Not(self._v)

    def equal(self, e):
        if self._v != e: raise AssertionError(f"Expected {e!r}, got {self._v!r}")
        return self
    def above(self, n):
        if not self._v > n: raise AssertionError(f"Expected {self._v} > {n}")
        return self
    def below(self, n):
        if not self._v < n: raise AssertionError(f"Expected {self._v} < {n}")
        return self
    def include(self, s):
        if str(s) not in str(self._v): raise AssertionError(f"Expected {self._v!r} to include {s!r}")
        return self
    def ok(self):
        if not self._v: raise AssertionError(f"Expected truthy, got {self._v!r}")
        return self
    def a(self, t: str):
        type_map = {"string": str, "number": (int, float), "boolean": bool,
                    "object": dict, "array": list}
        et = type_map.get(t)
        if et and not isinstance(self._v, et):
            raise AssertionError(f"Expected type {t}, got {type(self._v).__name__}")
        return self
    # aliases
    less_than    = below
    greater_than = above
    eql          = equal


# ── pm.response proxy ─────────────────────────────────────────────────────────

class RProxy:
    def __init__(self, r: "Response"):
        self._r = r

    @property
    def status(self) -> int: return self._r.status_code
    @property
    def body(self) -> str: return self._r.body
    @property
    def time(self) -> float: return self._r.elapsed_ms
    @property
    def size(self) -> int: return self._r.body_size

    def json(self) -> Any:
        return json.loads(self._r.body)
    def header(self, name: str) -> Optional[str]:
        return self._r.headers.get(name.lower())
    def text(self) -> str:
        return self._r.body


# ── pm context ────────────────────────────────────────────────────────────────

class EnvProxy:
    def __init__(self, env: "Env", scope: str = "env"):
        self._env = env; self._scope = scope
    def set(self, k: str, v: Any) -> None:
        self._env.set(k, str(v), self._scope)
    def get(self, k: str) -> Optional[str]:
        return self._env.get(k)


class PM:
    def __init__(self, env: "Env", response: Optional["Response"] = None):
        self.environment = EnvProxy(env, "env")
        self.globals     = EnvProxy(env, "global")
        self.response    = RProxy(response) if response else None
        self.headers: Dict[str, str] = {}
        self._assertions: List["Assertion"] = []

    def test(self, name: str, fn: Callable) -> None:
        from .models import Assertion
        try:
            fn()
            self._assertions.append(Assertion(name=name, passed=True))
        except Exception as e:
            self._assertions.append(Assertion(name=name, passed=False, message=str(e)))

    def expect(self, val: Any) -> Expect:
        return Expect(val)


# ── Engine ────────────────────────────────────────────────────────────────────

_SAFE = {
    "json": json, "len": len, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "range": range,
    "print": print, "any": any, "all": all, "sorted": sorted,
    "round": round, "abs": abs, "max": max, "min": min,
    "isinstance": isinstance, "hasattr": hasattr, "type": type,
}


def _run(code: str, ns: dict) -> Optional[str]:
    if not code or not code.strip():
        return None
    try:
        exec(compile(code, "<script>", "exec"), {**_SAFE, **ns})
        return None
    except Exception:
        return traceback.format_exc(limit=3)


def run_pre(code: str, env: "Env", headers: dict):
    pm = PM(env)
    pm.headers = headers
    err = _run(code, {"pm": pm})
    headers.update(pm.headers)
    return err


def run_test(code: str, env: "Env", response: "Response"):
    pm = PM(env, response)
    err = _run(code, {"pm": pm})
    # sync env changes back
    for k, v in env.clone().snapshot().items():
        pass  # already written through EnvProxy
    return pm._assertions, err
