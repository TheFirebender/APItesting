"""core/variables.py — разрешение {{переменных}}."""
from __future__ import annotations
import re
from typing import Dict, Optional

_RE = re.compile(r"\{\{(\w+)\}\}")


class Env:
    """Три уровня: global < env < local."""

    def __init__(self, global_vars: Dict[str, str] = None,
                 env_vars: Dict[str, str] = None,
                 local_vars: Dict[str, str] = None):
        self._g = dict(global_vars or {})
        self._e = dict(env_vars or {})
        self._l = dict(local_vars or {})

    def get(self, key: str) -> Optional[str]:
        return self._l.get(key) or self._e.get(key) or self._g.get(key)

    def set(self, key: str, value: str, scope: str = "env") -> None:
        if scope == "global":   self._g[key] = str(value)
        elif scope == "local":  self._l[key] = str(value)
        else:                   self._e[key] = str(value)

    def resolve(self, text: Optional[str]) -> str:
        if not text:
            return text or ""
        return _RE.sub(lambda m: self.get(m.group(1)) or m.group(0), str(text))

    def resolve_dict(self, d: Dict[str, str]) -> Dict[str, str]:
        return {self.resolve(k): self.resolve(v) for k, v in d.items()}

    def snapshot(self) -> Dict[str, str]:
        return {**self._g, **self._e, **self._l}

    def clone(self) -> "Env":
        return Env(dict(self._g), dict(self._e), dict(self._l))
