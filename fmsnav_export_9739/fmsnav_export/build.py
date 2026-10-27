"""Orquestrador: zip do ciclo -> JSONs (um por parametro) + planejador HTML.

Encadeia as etapas modulares:
    reader (decode) -> json_export (grava JSONs) -> html_builder (monta HTML)

A funcao build() e a API publica; o CLI esta em __main__.py.
"""
from __future__ import annotations

import time
from pathlib import Path

from .html_builder import build_html
from .json_export import export_json
from .reader import FmsDatabase


def build(zip_path, out="./out", cycle="2607", area=None, html_name="planejador.html"):
    """Le o zip binario e gera todos os JSONs e o HTML.

    Parametros
    ----------
    zip_path : caminho do zip do ciclo (contendo os .S01)
    out      : diretorio de saida (cria out/db/*.json e out/<html_name>)
    cycle    : rotulo do ciclo AIRAC (ex.: "2607")
    area     : filtro opcional por prefixo ICAO, ex.: ["SB"] para Brasil.
               None = mundo inteiro.
    """
    t0 = time.time()
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    areas = tuple(area) if area else None

    print(f"[1/3] lendo banco binario: {zip_path}")
    db = FmsDatabase(str(zip_path))
    print(f"      {db.summary()}")

    print("[2/3] exportando JSONs por parametro:")
    data = export_json(db, out_dir, cycle)

    print("[3/3] montando planejador HTML:")
    html_path = out_dir / html_name
    stats = build_html(data, html_path, cycle, areas)
    print(f"      payload {stats['raw_mb']:.1f} MB -> {stats['packed_mb']:.1f} MB comprimido")
    print(f"      {stats['nodes']:,} nos | {stats['edges']:,} arestas | "
          f"{stats['procs']:,} procedimentos")
    print(f"      {html_path}  ({stats['html_mb']:.2f} MB)")

    print(f"\nconcluido em {time.time()-t0:.1f}s -> {out_dir}/")
    return out_dir
