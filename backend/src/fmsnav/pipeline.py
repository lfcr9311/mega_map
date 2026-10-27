"""Pipeline de build: zip do ciclo -> JSONs por parametro + navgraph compilado."""
from __future__ import annotations

import time
from pathlib import Path

from .decode import FmsDatabase
from .export import EXTRACTORS, build_navgraph, export_json, write_navgraph

NAVGRAPH_FILE = "navgraph.json.gz"


def build(zip_path: str | Path, out: str | Path, cycle: str,
          area: list[str] | None = None, write_json: bool = True, log=print) -> Path:
    """Decodifica o zip e grava <out>/navgraph.json.gz (+ <out>/db/*.json).

    Retorna o caminho do navgraph, que e o que a API carrega.
    """
    t0 = time.time()
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    areas = tuple(area) if area else None

    log(f"[1/3] lendo banco binario: {zip_path}")
    db = FmsDatabase(zip_path)
    log(f"      {db.summary()}")

    log("[2/3] extraindo parametros")
    data = {name: fn(db) for name, fn in EXTRACTORS.items()}
    if write_json:
        export_json(data, out_dir, cycle, log=log)

    log("[3/3] compilando grafo de rotas")
    graph_path = out_dir / NAVGRAPH_FILE
    stats = write_navgraph(build_navgraph(data, areas), graph_path, cycle, areas)
    log(f"      {stats['nodes']:,} nos | {stats['edges']:,} arestas | {stats['procs']:,} procedimentos")
    log(f"      {graph_path}  ({stats['raw_mb']:.1f} MB -> {stats['file_mb']:.1f} MB)")

    log(f"\nconcluido em {time.time() - t0:.1f}s")
    return graph_path
