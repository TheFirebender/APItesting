"""core/reporter.py — JUnit XML / JSON / text отчёты (ФТ-5.3)."""
from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from typing import List

from .models import Result


def to_junit(results: List[Result], suite: str = "API Sentinel") -> str:
    total   = len(results)
    fails   = sum(1 for r in results if not r.passed)
    total_t = sum((r.response.elapsed_ms if r.response else 0) for r in results) / 1000

    root = ET.Element("testsuite", attrib={
        "name": suite, "tests": str(total),
        "failures": str(fails), "time": f"{total_t:.3f}",
    })
    for r in results:
        t_s = f"{(r.response.elapsed_ms / 1000):.3f}" if r.response else "0"
        tc  = ET.SubElement(root, "testcase",
                            attrib={"name": r.request_name, "classname": suite, "time": t_s})
        if r.error:
            ET.SubElement(tc, "error", attrib={"message": r.error}).text = r.error
        elif not r.passed:
            msgs = "; ".join(a.name for a in r.assertions if not a.passed)
            body = "\n".join(
                f"FAIL: {a.name}" + (f"\n  → {a.message}" if a.message else "")
                for a in r.assertions if not a.passed
            )
            ET.SubElement(tc, "failure", attrib={"message": msgs}).text = body
        if r.response:
            ET.SubElement(tc, "system-out").text = (
                f"Status: {r.response.status_code}  "
                f"Time: {r.response.elapsed_ms}ms  "
                f"Assertions: {sum(1 for a in r.assertions if a.passed)}/{len(r.assertions)}"
            )
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def to_json(results: List[Result], summary: dict) -> str:
    return json.dumps({"summary": summary,
                       "results": [r.to_dict() for r in results]},
                      ensure_ascii=False, indent=2)


def to_text(results: List[Result], summary: dict) -> str:
    SEP = "═" * 62
    lines = [f"\n{SEP}", "  API SENTINEL — РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ", SEP]
    for r in results:
        mark = "✓" if r.passed else "✗"
        info = (f"{r.response.status_code}  {r.response.elapsed_ms}мс"
                if r.response else r.error or "ERROR")
        lines.append(f"  {mark} {r.request_name:<44} {info}")
        for a in r.assertions:
            am = "  ✓" if a.passed else "  ✗"
            lines.append(f"    {am} {a.name}")
            if not a.passed and a.message:
                lines.append(f"       → {a.message}")
    lines += [
        "─" * 62,
        f"  Запросов:  {summary['total']} (✓{summary['passed']} ✗{summary['failed']})",
        f"  Тесты:     {summary['passed_assertions']}/{summary['total_assertions']}",
        f"  Ср. время: {summary['avg_ms']}мс",
        f"  Успех:     {summary['success_rate']}%",
        SEP,
    ]
    return "\n".join(lines)
