"""Grava um arquivo JSON por parametro em <out>/db/.

Cada JSON tem um cabecalho leve (parametro, ciclo, contagem) e o payload
cru do extrator, para o arquivo ser auto-descritivo.
"""
from __future__ import annotations

import json
from pathlib import Path

from .extractors import EXTRACTORS
from .reader import FmsDatabase


def _count(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return sum(len(v) if isinstance(v, list) else 1 for v in data.values())
    return 0


def export_json(db: FmsDatabase, out_dir: Path, cycle: str) -> dict[str, dict]:
    """Roda todos os extratores e grava <out>/db/<parametro>.json.

    Retorna um dict {parametro: data} para o html_builder reaproveitar sem
    reprocessar o banco.
    """
    db_dir = out_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, dict] = {}
    index = {"cycle": cycle, "files": {}}

    for name, fn in EXTRACTORS.items():
        data = fn(db)
        doc = {"parameter": name, "cycle": cycle, "count": _count(data), "data": data}
        path = db_dir / f"{name}.json"
        path.write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        result[name] = data
        index["files"][name] = {"file": f"db/{name}.json", "count": doc["count"]}
        print(f"    db/{name}.json  ({doc['count']:,} registros, "
              f"{path.stat().st_size/1e6:.2f} MB)")

    # indice geral para descoberta
    (db_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
