# Arquitetura

## Visão geral

```
           build (offline, ~50 s)                         runtime
┌──────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│ FMS_ciclo.zip (.S01)                 │   │  fmsnav serve (FastAPI, :8001)            │
│   └─ decode/   FmsDatabase           │   │    navgraph/  NavGraph (memória, ~1,5 s)  │
│        └─ export/ extractors         │   │    routing/   A*, SID/STAR, desvio        │
│             ├─ db/*.json             │   │    notams/    rpl_back (:8000) + cache    │
│             └─ navgraph.json.gz ─────┼──►│    api/       /api/*  + frontend/dist em / │
└──────────────────────────────────────┘   └───────────────▲──────────────────────────┘
                                                            │ JSON
                                           ┌────────────────┴──────────────────────────┐
                                           │ frontend (TS + Vite + Leaflet)             │
                                           │   api/ → app/controller → ui/ + map/       │
                                           └───────────────────────────────────────────┘
```

Decodificar o binário é lento (~50 s para o mundo), então acontece **uma vez por ciclo**
(`fmsnav build`) e produz um grafo compilado. A API só carrega esse grafo.

## Backend (`backend/src/fmsnav/`)

Dependências apontam sempre para baixo: `api → routing/notams → navgraph → geo`;
`export → decode → domain`.

| módulo | responsabilidade |
|---|---|
| `domain/models.py` | `Fix`, `Airport`, `Runway`, `Leg`, `Procedure`, `AirwayLeg` |
| `decode/primitives.py` | texto 6 bits, coordenadas uint24 — validadas 100% |
| `decode/tables.py` | layout das tabelas, PATH_TERM, nibbles de seção |
| `decode/database.py` | `FmsDatabase`: zip → objetos. **Fonte da verdade do formato** |
| `export/extractors.py` | um extrator por parâmetro (`EXTRACTORS`) |
| `export/json_export.py` | `db/<param>.json` |
| `export/navgraph_builder.py` | grafo compacto `{n,e,p,r}` + conectores terminais |
| `pipeline.py` | orquestra o build |
| `navgraph/graph.py` | `NavGraph`: adjacência, aerovia por perna, busca por ident/ICAO, índice espacial (grade de 1°), `VirtualPoint` |
| `routing/astar.py` | A* (heurística great-circle) e Dijkstra multi-alvo |
| `routing/procedures.py` | opções SID/STAR (ARINC 424), cadeia por pista, restrições de altitude |
| `routing/avoidance.py` | nós bloqueados, remoção de nós internos, coordenadas de escape |
| `routing/planner.py` | `RoutePlanner.plan()`: rota porta-a-porta |
| `notams/` | cliente do rpl_back, parsing de coordenadas, cache com TTL |
| `api/` | schemas Pydantic, dependências, routers |
| `settings.py` | configuração por `FMSNAV_*` |

### Planejamento (`RoutePlanner.plan`)

1. Resolve origem/destino; rota base por A* (nós em área de NOTAM custam ×10 000).
   Com `level` = `H`/`L`, o A* só anda por aerovias de alta/baixa — alta é todo designador
   que começa com `U` (`navgraph.airway_level`); conectores aeroporto↔malha valem sempre.
2. SID/STAR: chave explícita, `"auto"` ou nenhuma. Em `"auto"`, as opções são filtradas
   pela pista e a melhor combinação é a de menor distância total. Para não rodar um A* por
   par, roda um Dijkstra por fixo de saída distinto até todos os fixos de entrada.
3. Monta a cadeia: `origem + SID[:-1] + en-route + STAR[1:] + destino`. Se a rota foi
   editada (`edited`), preserva o miolo editado em vez de re-rotear.
4. Se ainda cruza área de NOTAM: remove os nós internos e insere coordenadas de escape
   (`WPTA1`, `WPTB2`…) só nos segmentos que cruzam. Se SID/STAR cruzam, cai para a rota
   direta sem procedimentos (e avisa em `warnings`).

### API

| método | rota | |
|---|---|---|
| GET | `/api/meta` | ciclo, contagens |
| GET | `/api/airports?q=` | autocomplete |
| GET | `/api/airports/{icao}` | detalhe + pistas |
| GET | `/api/airports/{icao}/procedures?kind=SID\|STAR&runway=` | opções |
| GET | `/api/network?south&west&north&east&fixes=&level=` | malha visível (desenho) |
| POST | `/api/route` | planejamento completo |
| POST | `/api/route/annotate` | resolve uma rota editada (sem re-rotear) |
| GET | `/api/notams` | áreas de NOTAM usadas no desvio |
| GET | `/api/special-areas` | repasse do rpl_back |

Pontos são referenciados por `id` (nó do grafo), por `ident` (resolvido pelo mais próximo
do ponto anterior) ou por `lat/lon` (ponto virtual). Os ids valem para o grafo carregado.
Depois de um rebuild, o frontend recalcula a rota.

## Frontend (`frontend/src/`)

| pasta | responsabilidade |
|---|---|
| `api/` | `types.ts` (espelho dos schemas) e `client.ts` (fetch tipado, `ApiError`) |
| `app/state.ts` | `RouteState` e helpers (`pointKey`, `legKey`, `coreFallback`) |
| `app/controller.ts` | fluxo: calcular → pistas → SID/STAR → edições |
| `map/` | `MapView` (Leaflet + overlay SVG), `NetworkLoader` (malha por bbox), `NotamLayer`, `basemaps` |
| `ui/` | autocomplete, seletor de pistas, dropdowns SID/STAR, tabela editável, mensagens |
| `styles/` | `base`, `sidebar`, `map` |

O frontend não tem lógica de roteamento. O DCT por perna é só apresentação (tracejado e
rótulo) e fica no cliente.

## Mudanças de comportamento em relação ao HTML antigo

- A SID/STAR montada usa a runway transition **da pista escolhida**. O antigo filtrava pela
  pista, mas montava sempre a primeira runway transition.
- Os NOTAMs de demonstração só entram com `FMSNAV_DEMO_NOTAMS=1`. Antes eles entravam
  sozinhos quando o rpl_back não respondia e desviavam rotas reais por áreas fictícias.
- `"auto"` com só um lado sem opções mantém o outro procedimento (antes descartava os dois).
- O fixo de destino na tabela não é editável. Para trocar o destino, use o formulário.
