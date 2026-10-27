# data/

- `cycles/<ciclo>/FMS_ciclo.zip` — zip do ciclo AIRAC com os `.S01` (Thales). Fonte única de dados.
- `build/` — gerado por `make data` (ou `fmsnav build`):
  - `navgraph.json.gz` — grafo compilado que a API carrega (`FMSNAV_GRAPH`)
  - `db/*.json` — um JSON por parâmetro decodificado (aeroportos, pistas, waypoints, aerovias, SIDs, STARs, aproximações)

Novo ciclo: coloque o zip em `cycles/<ciclo>/` e rode `make data CYCLE=<ciclo>`.
