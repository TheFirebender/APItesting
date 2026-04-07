#!/usr/bin/env python3
"""cli/apisent.py — CLI-инструмент. Запуск: python apisent.py --help"""
from __future__ import annotations
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.models import Request, Environment
from core.variables import Env
from core.executor import execute, run_collection, summarize
from core.reporter import to_junit, to_json, to_text
from core.storage import (
    gen_id, save_collection, list_collections, list_environments,
    save_environment, get_history, load_settings, Collection,
)

# ── ANSI ───────────────────────────────────────────────────────────────────────
IS_TTY = sys.stdout.isatty()
C = {
    "bold":   "\033[1m"  if IS_TTY else "",
    "dim":    "\033[2m"  if IS_TTY else "",
    "green":  "\033[32m" if IS_TTY else "",
    "red":    "\033[31m" if IS_TTY else "",
    "yellow": "\033[33m" if IS_TTY else "",
    "blue":   "\033[34m" if IS_TTY else "",
    "cyan":   "\033[36m" if IS_TTY else "",
    "reset":  "\033[0m"  if IS_TTY else "",
}
def c(s, col): return f"{C.get(col,'')}{s}{C['reset']}"

# ── helpers ────────────────────────────────────────────────────────────────────
def build_env(args) -> Env:
    env_vars: dict = {}
    if hasattr(args, "env") and args.env:
        for e in list_environments():
            if e.name == args.env or e.id == args.env:
                env_vars = dict(e.variables)
                break
        else:
            print(c(f"Предупреждение: окружение '{args.env}' не найдено", "yellow"),
                  file=sys.stderr)
    if hasattr(args, "var") and args.var:
        for pair in args.var:
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return Env(env_vars=env_vars)

# ── send ───────────────────────────────────────────────────────────────────────
def cmd_send(args):
    hdrs = {}
    if args.header:
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                hdrs[k.strip()] = v.strip()

    req = Request(
        id=gen_id(), name=f"{args.method} {args.url}",
        method=args.method.upper(), url=args.url,
        headers=hdrs,
        body_format=args.body_format or "none",
        body=args.body,
    )
    env = build_env(args)
    settings = load_settings()
    result = execute(req, env,
                     verify_ssl=not args.insecure,
                     timeout=args.timeout or settings["timeout"])

    print(c(f"\n→ {req.method} {args.url}", "bold"))

    if result.error:
        print(c(f"\n✗ {result.error}", "red"))
        sys.exit(1)

    resp = result.response
    col_map = {"green": "green", "yellow": "yellow", "red": "red", "blue": "blue"}
    print(c(f"\n● {resp.status_code} {resp.status_text}", col_map.get(resp.color, "reset")))
    print(c(f"● Время:  {resp.elapsed_ms}мс", "dim"))
    print(c(f"● Размер: {resp.body_size} байт", "dim"))

    if getattr(args, "show_headers", False):
        print(c("\n── Заголовки ─────────────────────────────", "dim"))
        for k, v in resp.headers.items():
            print(f"  {c(k, 'blue')}: {v}")

    print(c("\n── Тело ──────────────────────────────────", "dim"))
    if resp.is_json and not getattr(args, "raw", False):
        try:
            print(json.dumps(json.loads(resp.body), ensure_ascii=False, indent=2))
        except Exception:
            print(resp.body)
    else:
        print(resp.body)

# ── run ────────────────────────────────────────────────────────────────────────
def cmd_run(args):
    col = None
    for c_def in list_collections():
        if c_def.name == args.collection or c_def.id == args.collection:
            col = c_def; break
    if not col and os.path.isfile(args.collection):
        try:
            col = Collection.from_dict(json.loads(open(args.collection, encoding="utf-8").read()))
        except Exception as e:
            print(c(f"✗ Ошибка чтения файла: {e}", "red")); sys.exit(1)
    if not col:
        print(c(f"✗ Коллекция не найдена: {args.collection}", "red")); sys.exit(1)

    env = build_env(args)
    for k, v in col.variables.items():
        if not env.get(k): env.set(k, v)

    requests = col.all_requests()
    if getattr(args, "folder", None):
        for f in col.folders:
            if f.name == args.folder:
                requests = f.requests; break

    settings = load_settings()

    print(c(f"\n▶ Коллекция: {col.name}", "bold"))
    print(c(f"  Запросов: {len(requests)}\n", "dim"))

    def on_result(r):
        mark = c("✓", "green") if r.passed else c("✗", "red")
        if r.response:
            col_map = {"green":"green","yellow":"yellow","red":"red","blue":"cyan"}
            st = c(str(r.response.status_code), col_map.get(r.response.color,"reset"))
            ms = c(f"{r.response.elapsed_ms}мс", "dim")
            print(f"  {mark} {r.request_name:<44} {st}  {ms}")
        else:
            print(f"  {mark} {r.request_name:<44} {c(r.error or 'ERROR','red')}")
        for a in r.assertions:
            am = c("  ✓","green") if a.passed else c("  ✗","red")
            print(f"    {am} {a.name}")
            if not a.passed and a.message:
                print(c(f"       → {a.message}", "yellow"))

    results = run_collection(requests, env,
                             verify_ssl=not getattr(args,"insecure",False),
                             timeout=getattr(args,"timeout",None) or settings["timeout"],
                             on_result=on_result)
    s = summarize(results)
    fmt = getattr(args, "output_format", "text") or "text"

    if fmt == "junit":
        xml = to_junit(results, col.name)
        if getattr(args,"output",None):
            open(args.output,"w",encoding="utf-8").write(xml)
            print(c(f"\n  JUnit XML сохранён: {args.output}", "green"))
        else:
            print(xml)
    elif fmt == "json":
        js = to_json(results, s)
        if getattr(args,"output",None):
            open(args.output,"w",encoding="utf-8").write(js)
            print(c(f"\n  JSON сохранён: {args.output}", "green"))
        else:
            print(js)
    else:
        print(to_text(results, s))

    sys.exit(1 if s["failed"] > 0 else 0)

# ── collection ─────────────────────────────────────────────────────────────────
def cmd_collection(args):
    sub = getattr(args, "col_cmd", "list")
    if sub == "list":
        cols = list_collections()
        print(c("\n  Коллекции:\n", "bold"))
        if not cols: print(c("  (нет коллекций)", "dim")); return
        for col in cols:
            n = len(col.all_requests())
            print(f"  {c('•','blue')} {col.name:<36} {c(col.id,'dim')}  {c(str(n)+' req','dim')}")
        print()
    elif sub == "new":
        cid = gen_id()
        save_collection(Collection(id=cid, name=args.name))
        print(c(f"\n  ✓ Коллекция создана: {args.name}  ({cid})\n", "green"))

# ── env ────────────────────────────────────────────────────────────────────────
def cmd_env(args):
    sub = getattr(args, "env_cmd", "list")
    if sub == "list":
        envs = list_environments()
        print(c("\n  Окружения:\n", "bold"))
        if not envs: print(c("  (нет окружений)", "dim")); return
        for e in envs:
            n = len(e.variables)
            print(f"  {c('•','cyan')} {e.name:<30} {c(e.id,'dim')}  {c(str(n)+' vars','dim')}")
        print()
    elif sub == "new":
        variables = {}
        if getattr(args, "var", None):
            for pair in args.var:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    variables[k.strip()] = v.strip()
        eid = gen_id()
        save_environment(Environment(id=eid, name=args.name, variables=variables))
        print(c(f"\n  ✓ Окружение создано: {args.name}  ({eid})\n", "green"))

# ── history ────────────────────────────────────────────────────────────────────
def cmd_history(args):
    limit = getattr(args, "limit", 20) or 20
    hist  = get_history(limit)
    print(c(f"\n  История (последние {len(hist)}):\n", "bold"))
    if not hist: print(c("  (пусто)", "dim")); return
    for h in hist:
        ts   = (h.get("timestamp","")[:19]).replace("T"," ")
        mark = c("✓","green") if h.get("passed") else c("✗","red")
        code = h.get("response",{}).get("status_code","—") if h.get("response") else "—"
        ms_v = h.get("response",{}).get("elapsed_ms") if h.get("response") else None
        ms   = f"{round(ms_v)}мс" if ms_v else ""
        print(f"  {mark} {ts}  {(h.get('request_name','')):<36}  {str(code):>3}  {ms}")
    print()

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(prog="apisent",
        description="API Sentinel — HTTP-клиент для тестирования API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Примеры:
  apisent send https://jsonplaceholder.typicode.com/posts/1
  apisent send https://api.example.com/users -m POST -b '{"name":"test"}' --body-format json
  apisent run "JSONPlaceholder Demo" --output-format junit -o report.xml
  apisent env new production --var BASE_URL=https://api.example.com""")

    sp = p.add_subparsers(dest="cmd")

    # send
    ps = sp.add_parser("send", help="Отправить HTTP-запрос")
    ps.add_argument("url")
    ps.add_argument("-m","--method", default="GET")
    ps.add_argument("-H","--header", action="append", metavar="Key: Value")
    ps.add_argument("-b","--body")
    ps.add_argument("--body-format", dest="body_format")
    ps.add_argument("--env")
    ps.add_argument("--var", action="append", metavar="KEY=VALUE")
    ps.add_argument("--insecure", action="store_true")
    ps.add_argument("--timeout", type=int, default=30)
    ps.add_argument("--show-headers", action="store_true")
    ps.add_argument("--raw", action="store_true")

    # run
    pr = sp.add_parser("run", help="Запустить коллекцию")
    pr.add_argument("collection")
    pr.add_argument("--env")
    pr.add_argument("--var", action="append", metavar="KEY=VALUE")
    pr.add_argument("--folder")
    pr.add_argument("--output-format", dest="output_format",
                    choices=["text","junit","json"], default="text")
    pr.add_argument("-o","--output")
    pr.add_argument("--insecure", action="store_true")
    pr.add_argument("--timeout", type=int)

    # collection
    pc = sp.add_parser("collection", help="Управление коллекциями")
    csp = pc.add_subparsers(dest="col_cmd")
    csp.add_parser("list")
    cn = csp.add_parser("new")
    cn.add_argument("name")

    # env
    pe = sp.add_parser("env", help="Управление окружениями")
    esp = pe.add_subparsers(dest="env_cmd")
    esp.add_parser("list")
    en = esp.add_parser("new")
    en.add_argument("name")
    en.add_argument("--var", action="append", metavar="KEY=VALUE")

    # history
    ph = sp.add_parser("history", help="История запросов")
    ph.add_argument("--limit", type=int, default=20)

    args = p.parse_args()
    if not args.cmd:
        p.print_help(); return

    dispatch = {
        "send": cmd_send, "run": cmd_run,
        "collection": cmd_collection, "env": cmd_env, "history": cmd_history,
    }
    dispatch.get(args.cmd, lambda a: p.print_help())(args)

if __name__ == "__main__":
    main()
