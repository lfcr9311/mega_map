"""fmsnav_export — le o banco binario .S01 (dentro do zip do ciclo) e gera:

  - um JSON por parametro decodificado (waypoints, aeroportos, pistas,
    aerovias, procedimentos), em ./out/db/
  - um planejador HTML standalone (Leaflet) que consome esses JSONs embutidos.

Uso rapido:

    python -m fmsnav_export CICLO.zip --cycle 2607 --out ./out

Modular por design: reader (decode) -> extractors (parametro->dict) ->
json_export (grava JSONs) -> html_builder (monta o HTML). O orquestrador
build.py apenas encadeia essas etapas.
"""
from .reader import FmsDatabase
from .build import build

__all__ = ["FmsDatabase", "build"]
