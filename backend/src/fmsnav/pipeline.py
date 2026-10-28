"""Pipeline de build: zip do ciclo -> JSONs por parametro + navgraph compilado."""
from __future__ import annotations

import time
from pathlib import Path

from .decode import FmsDatabase
from .export import EXTRACTORS, apply_directions, build_navgraph, export_json, write_navgraph

NAVGRAPH_FILE = "navgraph.json.gz"


def build(zip_path: str | Path, out: str | Path, cycle: str,
          area: list[str] | None = None, write_json: bool = True,
          aip_cache: str | Path | None = None, log=print) -> Path:
    """Decodifica o zip e grava <out>/navgraph.json.gz (+ <out>/db/*.json).

    `aip_cache` = pasta de cache da eAIP: o sentido das aerovias brasileiras
    vem dela (o banco do FMS nao tem). None = sem sentido (tudo mao dupla).
    Retorna o caminho do navgraph, que e o que a API carrega.
    """
    t0 = time.time()
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    areas = tuple(area) if area else None

    log(f"[1/4] lendo banco binario: {zip_path}")
    db = FmsDatabase(zip_path)
    log(f"      {db.summary()}")

    log("[2/4] extraindo parametros")
    data = {name: fn(db) for name, fn in EXTRACTORS.items()}
    if write_json:
        export_json(data, out_dir, cycle, log=log)

    log("[3/4] compilando grafo de rotas")
    graph = build_navgraph(data, areas)

    directions = None
    if aip_cache:
        from .aip import fetch_segments
        log("[4/4] sentido das aerovias (eAIP DECEA, ENR 3.2)")
        amdt, segments, problems = fetch_segments(cycle, Path(aip_cache), log=log)
        rep = apply_directions(graph, segments)
        directions = {"source": f"eAIP DECEA {amdt}", "segments": rep["segments"],
                      "one_way": rep["one_way"], "marked_edges": rep["marked"],
                      "missing": len(rep["missing"])}
        log(f"      {rep['segments']:,} trechos | {rep['one_way']:,} de sentido unico | "
            f"{rep['marked']:,} pernas marcadas | {len(rep['missing'])} trechos sem perna no banco")
        for msg in problems + [f"sem perna no banco: {m}" for m in rep["missing"]]:
            log(f"      ! {msg}")
    else:
        log("[4/4] sentido das aerovias: desligado (todas de mao dupla)")

    graph_path = out_dir / NAVGRAPH_FILE
    stats = write_navgraph(graph, graph_path, cycle, areas, directions)
    log(f"      {stats['nodes']:,} nos | {stats['edges']:,} arestas | {stats['procs']:,} procedimentos")
    log(f"      {graph_path}  ({stats['raw_mb']:.1f} MB -> {stats['file_mb']:.1f} MB)")

    log(f"\nconcluido em {time.time() - t0:.1f}s")
    return graph_path
