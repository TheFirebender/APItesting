"""core/storage.py — хранение в ~/.api-sentinel-py/ (JSON, совместимо с Git)."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from .models import Collection, Environment

BASE   = Path.home() / ".api-sentinel-py"
C_DIR  = BASE / "collections"
E_DIR  = BASE / "environments"
H_FILE = BASE / "history.json"
S_FILE = BASE / "settings.json"

for d in (C_DIR, E_DIR): d.mkdir(parents=True, exist_ok=True)


def gen_id() -> str:
    return uuid.uuid4().hex[:8]


# ── Collections ────────────────────────────────────────────────────────────────

def save_collection(col: Collection) -> Path:
    p = C_DIR / f"{col.id}.json"
    p.write_text(json.dumps(col.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    return p

def load_collection(cid: str) -> Optional[Collection]:
    p = C_DIR / f"{cid}.json"
    if not p.exists(): return None
    return Collection.from_dict(json.loads(p.read_text("utf-8")))

def list_collections() -> List[Collection]:
    result = []
    for p in sorted(C_DIR.glob("*.json")):
        try: result.append(Collection.from_dict(json.loads(p.read_text("utf-8"))))
        except Exception: pass
    return result

def delete_collection(cid: str) -> bool:
    p = C_DIR / f"{cid}.json"
    if p.exists(): p.unlink(); return True
    return False


# ── Environments ───────────────────────────────────────────────────────────────

def save_environment(env: Environment) -> Path:
    p = E_DIR / f"{env.id}.json"
    p.write_text(json.dumps(env.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    return p

def list_environments() -> List[Environment]:
    result = []
    for p in sorted(E_DIR.glob("*.json")):
        try: result.append(Environment.from_dict(json.loads(p.read_text("utf-8"))))
        except Exception: pass
    return result

def delete_environment(eid: str) -> bool:
    p = E_DIR / f"{eid}.json"
    if p.exists(): p.unlink(); return True
    return False


# ── History ────────────────────────────────────────────────────────────────────

def append_history(entry: dict) -> None:
    hist = _load_raw_history()
    hist.append({**entry, "timestamp": datetime.utcnow().isoformat()})
    if len(hist) > 500: hist = hist[-500:]
    H_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), "utf-8")

def get_history(limit: int = 100) -> list:
    return list(reversed(_load_raw_history()[-limit:]))

def clear_history() -> None:
    if H_FILE.exists(): H_FILE.unlink()

def _load_raw_history() -> list:
    if not H_FILE.exists(): return []
    try:   return json.loads(H_FILE.read_text("utf-8"))
    except Exception: return []


# ── Settings ───────────────────────────────────────────────────────────────────

_DEFAULTS = {"active_env": None, "verify_ssl": True, "timeout": 30, "theme": "dark"}

def load_settings() -> dict:
    if not S_FILE.exists(): return dict(_DEFAULTS)
    try:   return {**_DEFAULTS, **json.loads(S_FILE.read_text("utf-8"))}
    except Exception: return dict(_DEFAULTS)

def save_settings(s: dict) -> None:
    S_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), "utf-8")
