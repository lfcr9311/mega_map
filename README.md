# FMSNAV — planejador de rotas sobre o banco FMS

Decodifica o banco de navegação binário do FMS Thales (`.S01`, ciclo AIRAC) e oferece um
planejador de rotas porta-a-porta: SID → aerovias (A*) → STAR, com escolha automática de
procedimentos por pista, edição manual da rota e desvio de áreas de NOTAM.

```
backend/   Python + FastAPI — decoder, grafo, roteamento, API
frontend/  TypeScript + Vite + Leaflet — interface e mapa
data/      zip do ciclo e grafo compilado
docs/      ARQUITETURA.md (como o sistema é organizado)
           DOCUMENTACAO_COMPLETA.md (engenharia reversa do formato binário)
```

## Rodando

Pré-requisitos: Python ≥ 3.11 e Node ≥ 20.

```bash
make install        # venv + npm install
make data           # decodifica data/cycles/2610/FMS_ciclo.zip -> data/build/ (~50 s)
                    #   + sentido das aerovias da eAIP do DECEA (1a vez baixa, ~1 min)
make serve          # compila o frontend e sobe tudo em http://127.0.0.1:8001/map/
```

Desenvolvimento, em dois terminais:

```bash
make api            # API com reload em :8001
make web            # Vite em http://localhost:5173/map/ (proxy /map/api -> :8001)
```

Testes: `make test` (pytest + typecheck).

Link direto para uma rota: `http://127.0.0.1:8001/map/?o=SBGR&d=SBBR` (`&level=H` só alta, `&level=L` só baixa).

Pelo terminal, sem servidor: `backend/.venv/bin/fmsnav route SBGR SBBR --rwy-dep 10 --rwy-arr 11 --sid auto --star auto --level H`.

## Configuração (variáveis de ambiente)

| variável | default | |
|---|---|---|
| `FMSNAV_GRAPH` | `data/build/navgraph.json.gz` | grafo carregado pela API |
| `FMSNAV_RPL_BACK_URL` | `http://localhost:8000` | rpl_back (NOTAMs, áreas especiais); vazio desliga |
| `FMSNAV_NOTAM_ICAOS` | `SBCW,SBBS,SBRE,SBAZ` | FIRs consultadas no rpl_back |
| `FMSNAV_NOTAM_TTL_S` | `300` | cache dos NOTAMs |
| `FMSNAV_DEMO_NOTAMS` | `0` | `1` = usa 2 polígonos fictícios quando não há NOTAMs |
| `FMSNAV_CORS_ORIGINS` | `http://localhost:5173` | |

Documentação interativa da API: `http://127.0.0.1:8001/map/docs`.

## Deploy

Push no `master` publica em `http://ec2-3-137-219-87.us-east-2.compute.amazonaws.com/map/`
(GitHub Actions). Configuração inicial e grafo: [deploy/README.md](deploy/README.md).

## Legado

`fmsnav_export_9739/` e `planejador-mundial_5126.html` são a versão anterior (HTML
standalone com tudo no navegador). O decoder foi portado sem mudanças: os JSONs e o grafo
gerados são idênticos byte a byte aos do pipeline antigo.
