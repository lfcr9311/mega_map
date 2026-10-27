# fmsnav_export

Le o banco de navegacao binario do FMS Thales (arquivos `.S01` dentro do zip
do ciclo AIRAC) e gera:

- **um JSON por parametro** decodificado, em `<out>/db/`
- um **planejador HTML** standalone (Leaflet) que consome esse banco embutido

Nao depende de nenhum CSV — le tudo direto do binario.

## Uso

```bash
python -m fmsnav_export CICLO.zip --cycle 2607 --out ./out
```

Filtrando por area (prefixo ICAO, ex.: Brasil):

```bash
python -m fmsnav_export CICLO.zip --cycle 2607 --area SB --out ./out
```

Opcoes:

| flag | default | descricao |
|------|---------|-----------|
| `zip` | — | zip do ciclo com os `.S01` (obrigatorio) |
| `--out` | `./out` | diretorio de saida |
| `--cycle` | `2607` | rotulo do ciclo AIRAC |
| `--area` | (mundo) | prefixo(s) ICAO, separados por virgula (ex.: `SB` ou `SB,SA`) |
| `--html-name` | `planejador.html` | nome do HTML de saida |

Como biblioteca:

```python
from fmsnav_export import build
build("CICLO.zip", out="./out", cycle="2607", area=["SB"])
```

## Saida

```
out/
  planejador.html          # planejador standalone (abre no navegador)
  db/
    index.json             # indice dos arquivos + contagens
    airports.json          # ICAO + posicao
    runways.json           # cabeceira, proa, comprimento, elevacao (por aeroporto)
    waypoints.json         # fixos en-route + terminais (dedup)
    airways.json           # pernas de aerovia: designador + par de fixos + km
    sids.json              # SIDs por aeroporto, com restricoes de altitude
    stars.json             # STARs por aeroporto, com restricoes de altitude
    approaches.json        # aproximacoes por aeroporto
```

Cada JSON e auto-descritivo:

```json
{ "parameter": "airways", "cycle": "2607", "count": 49019, "data": [ ... ] }
```

## Arquitetura (modular)

```
reader.py        decodifica os .S01 -> objetos (Fix, Airport, Runway, Procedure, AirwayLeg)
extractors.py    um extrator por parametro: reader -> dict serializavel
json_export.py   grava um JSON por parametro em out/db/
html_builder.py  monta o payload compacto do grafo e injeta no template
build.py         orquestra: reader -> json_export -> html_builder
__main__.py      CLI
templates/
  planner.html   shell do planejador (UI + Leaflet + logica) com placeholders
```

Adicionar um parametro novo = escrever um extrator em `extractors.py` e
registra-lo no dict `EXTRACTORS`. Ele passa a virar JSON automaticamente.

## Parametros decodificados e validados

- Waypoints en-route e terminais (lat/lon), aeroportos, pistas — 100% vs CSV
- SID / STAR / aproximacao: sequencia de fixos, path & termination
- Restricao de altitude por fixo: valor + descritor (`+` no ou acima, `-` no ou
  abaixo, `''` exata, `B` janela) — decodificado e validado
- Aerovias: designador + delimitacao correta (calibrada vs CSV ER, sem DCT
  falso); ~91,5% das pernas confirmadas contra o CSV

## Planejador HTML

- Rota por aerovias publicadas entre dois ICAO (A*)
- SID/STAR conectados corretamente (transicao en-route + runway, unidos no
  fixo comum do procedimento)
- Tabela en-route **editavel**: campo livre por fixo, inserir/remover linha
- Alternar aerovia <-> **DCT** por perna (linha reta, sem re-rotear)
- Coluna de aerovia e restricao de altitude por fixo
- Edicoes persistem ao trocar SID/STAR (so zeram ao recalcular)
- Toggle de nomes dos waypoints no mapa (com zoom)
