"""Grava um JSON por parametro em <out>/db/.

Cada JSON e auto-descritivo: {"parameter", "cycle", "count", "data"}.
"""
from __future__ import annotations

import json
from pathlib import Path


def _count(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return sum(len(v) if isinstance(v, list) else 1 for v in data.values())
    return 0


def export_json(data: dict[str, object], out_dir: Path, cycle: str, log=print) -> None:
    db_dir = out_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    index: dict = {"cycle": cycle, "files": {}}

    for name, payload in data.items():
        doc = {"parameter": name, "cycle": cycle, "count": _count(payload), "data": payload}
        path = db_dir / f"{name}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index["files"][name] = {"file": f"db/{name}.json", "count": doc["count"]}
        log(f"    db/{name}.json  ({doc['count']:,} registros, {path.stat().st_size / 1e6:.2f} MB)")

    (db_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
