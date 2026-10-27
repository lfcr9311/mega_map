# FMS Nav Database — Engenharia Reversa, Decodificação e Planejador de Rotas

**Documento técnico completo.** Descreve, de ponta a ponta, como o banco de
navegação binário do FMS Thales (arquivos `.S01` dentro do zip de um ciclo
AIRAC) foi decodificado por engenharia reversa, como os parâmetros são
extraídos e validados, como o grafo de rotas é montado, como o otimizador (A*)
encontra a rota por aerovias, e como o planejador HTML conecta procedimentos
(SID/STAR) e permite edição manual.

O objetivo é que um programador/arquiteto — humano ou o próprio Claude numa
sessão futura — consiga entender, reconstruir e estender tudo sem informação
faltando.

---

## 0. Panorama

```
zip do ciclo AIRAC
   │  (contém arquivos *.S01, binários proprietários Thales)
   ▼
reader.py  ──►  decodifica cada tabela .S01 em objetos Python
   │             (Fix, Airport, Runway, Procedure, AirwayLeg)
   ▼
extractors.py ─► um extrator por parâmetro → dict serializável
   │
   ├──► json_export.py ─► um JSON por parâmetro (out/db/*.json)
   │
   └──► html_builder.py ─► payload compacto {n,e,p,r} → HTML standalone
                             (Leaflet + A* + montagem de rotas no cliente)
```

Nenhum CSV é usado em produção: **todo o conteúdo vem do binário**. Os CSVs
oficiais da Thales foram usados apenas como gabarito durante a engenharia
reversa (validação), e não são necessários para rodar.

### Ciclos usados
- 2607: binário `FMS.zip`; CSVs de validação `THALES_2607_FULL.zip`
- 2606: binário `2606_DB.zip`; CSVs `THALES_2606_FULL.zip`

---

## 1. Primitivas de decodificação

Três primitivas explicam a maioria dos campos. Todas validadas 100% contra os
CSVs oficiais.

### 1.1 Texto — identificadores de 6 bits

Cada caractere ocupa 6 bits dentro de um `uint32` big-endian. Os cinco
caracteres de um ident ficam nos deslocamentos `26, 20, 14, 8, 2`:

```python
CHARS = {0: "", 11: "-"}
CHARS.update({14 + i: str(i) for i in range(10)})   # dígitos 0-9  → códigos 14-23
CHARS.update({30 + i: chr(65 + i) for i in range(26)})  # letras A-Z → códigos 30-55
_SHIFTS = (26, 20, 14, 8, 2)

def decode_ident(v: int) -> str:                    # uint32 → até 5 chars
    return "".join(CHARS.get((v >> s) & 0x3F, "?") for s in _SHIFTS).strip()
```

Mapa de códigos de 6 bits:
- `0`   → vazio (padding)
- `11`  → hífen `-`
- `14..23` → dígitos `0..9`
- `30..55` → letras `A..Z`

**Nomes de 6 caracteres** (procedimentos como `ALON1B`): os 5 primeiros vêm do
`uint32` normal; o sexto caractere está nos bits 32..37 do `uint64` do registro:

```python
def decode_name6(rec: bytes) -> str:
    head  = decode_ident(int.from_bytes(rec[0:4], "big"))
    sixth = CHARS.get((int.from_bytes(rec[0:8], "big") >> (64 - 38)) & 0x3F, "")
    return (head + sixth).strip()
```

### 1.2 Coordenadas — inteiros de 24 bits com escala fixa

```python
def decode_lat(rec, off):                # uint24 BE / 80000 graus
    v = int.from_bytes(rec[off:off+3], "big") / 80000.0
    return v - 2**24/80000.0 if v > 90 else v      # complemento acima de 90°

def decode_lon(rec, off):                # uint24 BE / 40000 graus
    v = int.from_bytes(rec[off:off+3], "big") / 40000.0
    return v - 2**24/40000.0 if v > 180 else v     # complemento acima de 180°
```

Latitude: 24 bits, escala `1/80000` grau (≈0.045″). Longitude: escala
`1/40000` grau. Valores acima do range representam o hemisfério
sul/oeste por complemento (subtrai `2²⁴/escala`).

### 1.3 Ponteiros — dois esquemas de escala

O banco é um conjunto de tabelas de registros fixos que se referenciam por
ponteiros. Há **dois esquemas de escala**, e confundi-los foi fonte de bug:

| Contexto | Fórmula do índice | Observação |
|----------|-------------------|------------|
| `AWY_SEQ` (ponteiro de fixo) | `idx = (offset // 32) - 1`, com `code = ptr >> 24` selecionando a tabela | byte alto = código de tabela |
| Sequências de procedimento | `idx = ((ptr >> 5) // 16) - 1` | tabela vem do nibble do byte +3 |
| Cabeçalho de procedimento (primeira linha) | `first = (ptr >> 7) - 1` | idem AIRWAY.S01 |
| `AIRWAY.S01` (início da aerovia) | `start = (ptr >> 7) - 1` | **calibrado com erro zero vs CSV** |

> **Lição aprendida:** usei por engano `(ptr>>5)-4` para o AIRWAY.S01, o que
> produzia índices absurdos (até 231552 num arquivo de 57891 entradas) e
> aerovias que davam a volta ao mundo. A escala correta é `(ptr>>7)-1`.

---

## 2. Layout das tabelas (.S01)

Cada `.S01` é um array de registros de tamanho fixo (`rs`). Tabelas de fixos
decodificadas e validadas 100%:

| Arquivo | rs | Conteúdo | lat off | lon off | Notas |
|---------|----|----------|---------|---------|-------|
| `WPT_ENRT.S01` | 16 | waypoints en-route | 8 | 12 | |
| `WPT_TERM.S01` | 16 | waypoints terminais | 4 | 8 | |
| `AIRPORT.S01` | 40 | aeroportos | 4 | 8 | ident = ICAO |
| `RUNWAY.S01` | 20 | pistas | 4 | 8 | ver 2.1 |
| `VOR.S01` | 28 | VOR | 4 | 8 | navaid |
| `VOR_DMEC.S01` | 32 | VOR/DME colocalizado | 4 | 8 | sufixo C/N no ident |
| `VOR_DMEN.S01` | 20 | VOR/DME não-coloc. | 4 | 8 | |
| `DME.S01` | 32 | DME | 4 | 8 | |
| `NDB_ENRT.S01` | 28 | NDB en-route | 4 | 8 | |
| `NDB_TERM.S01` | 16 | NDB terminal | 4 | 8 | |

Tabelas de estrutura:

| Arquivo | Conteúdo |
|---------|----------|
| `AWY_SEQ.S01` | lista sequencial de ponteiros de fixos de aerovia (rs=8) |
| `AIRWAY.S01` | designadores de aerovia + ponteiro de início (rs=8) |
| `SID.S01`/`STAR.S01`/`APPR.S01` | cabeçalhos de procedimento (rs=20) |
| `SID_SEQ.S01`/... | sequências de pernas de procedimento (rs=24) |
| `ARPT_SID.S01`/... | ligação aeroporto→procedimento (rs=8) |

### 2.1 Pistas (`RUNWAY.S01`, rs=20)

```python
brg      = int.from_bytes(r[12:14], "big") / 160.0        # proa magnética
elev_raw = int.from_bytes(r[14:16], "big")
elev     = (elev_raw - 65536)/4 if elev_raw > 60000 else elev_raw/4   # pés
length   = int.from_bytes(r[16:18], "big") * 2            # pés
apt_ref  = int.from_bytes(r[0:4], "big")                  # referência ao aeroporto
```

O ident de cabeceira (`RW34`) **não** é armazenado — é derivado da proa:
`num = round(brg/10)` (ex.: 342° → `RW34`). A ligação pista→aeroporto é feita
por proximidade geográfica (o campo +0 não é um índice limpo).

---

## 3. Waypoints, aeroportos, pistas — extração direta

Cada tabela de fixo vira uma lista de `Fix(ident, lat, lon, kind)` iterando
sobre os registros de tamanho `rs`. Aeroportos e pistas idem. Isso é o núcleo
validado 100% contra o CSV. Ver `reader._read_fix_table`, `_read_airports`,
`_read_runways`.

---

## 4. Aerovias — o problema mais difícil da malha

### 4.1 Estrutura

- `AWY_SEQ.S01` é uma **lista plana** de ponteiros de fixos (uma entrada por
  linha do CSV ER). Cada ponteiro resolve um fixo via `_airway_fix`.
- `AIRWAY.S01` dá, para cada aerovia, o **designador** (`decode_ident` dos
  primeiros 4 bytes) e o **índice de início** no `AWY_SEQ`
  (`start = (ptr>>7) - 1`).

### 4.2 Delimitação correta (a chave)

Os registros de `AIRWAY.S01` estão em **ordem crescente de início no arquivo** e
**particionam** o `AWY_SEQ` sem buracos. Portanto:

> O fim de cada aerovia = o início do **próximo registro na ordem do arquivo**
> (NÃO ordenado por nome).

Um mesmo designador (ex.: `M725`) aparece em **vários registros consecutivos** —
são sub-segmentos regionais, cada um uma corrida própria. Isso evita ligar
fixos de regiões diferentes com o mesmo nome de aerovia.

```python
# reader.airways()
recs = []
for i in range(len(awy) // 8):
    name  = decode_ident(int.from_bytes(awy[i*8 : i*8+4], "big"))
    start = (int.from_bytes(awy[i*8+4 : i*8+8], "big") >> 7) - 1   # ESCALA CORRETA
    recs.append((name, start))

for k, (name, start) in enumerate(recs):
    end = recs[k+1][1] if k+1 < len(recs) else n_seq   # fim = início do próximo
    prev = None
    for i in range(start, end):
        fix = self._airway_fix(struct.unpack_from(">I", buf, i*8)[0])
        if fix is not None and prev is not None:
            if _haversine(prev, fix) < 300:      # guarda anti-DCT-falso
                yield AirwayLeg(name, prev, fix)
        prev = fix
```

### 4.3 Guarda de 300 km

Mesmo com as fronteiras certas, dentro de uma corrida podem aparecer saltos
falsos (fixos não perfeitamente sequenciais). O limiar de `< 300 km` corta
pernas espúrias (ex.: o infame `DIDAB→NIPDA` de 558 km que aparecia como um DCT
gigante no mapa) sem remover pernas continentais legítimas (as maiores ficam
~250 km).

### 4.4 Validação

- 49019 pernas, **todas com designador**
- 0 pernas > 300 km
- **91,5%** dos pares confirmados contra o CSV ER (mesma aerovia + ordem)
- resíduo de 8,5% = fixos de fronteira de FIR (sufixo `...C`) e diferenças de
  direção — não são DCTs falsos

---

## 5. Procedimentos (SID / STAR / Aproximação)

### 5.1 Montagem

Três arquivos por tipo: ligação (`ARPT_*`), cabeçalho (`SID/STAR/APPR.S01`),
sequência (`*_SEQ.S01`, rs=24).

```python
# reader._procedures(kind)
for i in range(len(link) // 8):
    a, b = struct.unpack_from(">II", link, i*8)   # a=aeroporto, b=cabeçalho
    h = b - 1
    rec = hdr[h*20 : h*20+20]
    first = (int.from_bytes(rec[8:12], "big") >> 7) - 1   # 1ª linha no SEQ
    starts.append((a - 1, h, first))
# fim de cada procedimento = início do próximo (bounds ordenados)
```

O **nome** vem de `decode_name6(rec)` (6 chars); a **transição** de
`decode_ident(rec[12:16])`.

### 5.2 Registro de perna (SEQ, 24 bytes)

Campos decodificados e validados:

| Campo | Offset/bits | Fórmula |
|-------|-------------|---------|
| Path & Termination | byte 0 | `PATH_TERM[sr[0]]` (TF, CF, DF, CA, ...) |
| Altitude (valor) | bytes 1-2 | `uint16 BE` |
| **Descritor de altitude** | byte 3, bits 4-5 | `{0:'+',1:'-',2:'',3:'B'}[(sr[3]>>4)&3]` |
| Ponteiro do fixo | bytes 4-7 | ver 5.3 |
| Seção/tabela do fixo | byte 3, nibble baixo | seleciona a tabela alvo |
| RNP | byte 12 | `sr[12] * 5 / 100` |
| Distância | bytes 14-15 | `uint16 BE // 16` |

**Descritor de altitude** (validado 100%, 288448/288448):
- `+` → no ou acima (at-or-above)
- `-` → no ou abaixo (at-or-below)
- `` (vazio) → exata (hard)
- `B` → janela entre dois limites (between)

### 5.3 Resolução do fixo da perna (`_seq_fix`) — a parte delicada

O ponteiro sozinho é **ambíguo** entre `WPT_TERM` e `WPT_ENRT`. A tabela alvo
vem do **nibble baixo do byte +3**:

```python
SECTION_TABLE = {
    0x0: ("AIRPORT.S01", 40), 0x1: ("RUNWAY.S01", 20),
    0x2: ("WPT_ENRT.S01", 16), 0x3: ("WPT_TERM.S01", 16),
    0x7: ("VOR.S01", 28), 0x8: ("DME.S01", 32), 0x9: ("VOR_DMEC.S01", 32),
    0xA: ("VOR_DMEN.S01", 20), 0xB: ("NDB_ENRT.S01", 28), 0xC: ("NDB_TERM.S01", 16),
}
idx = ((ptr >> 5) // 16) - 1     # escala de sequência
```

**Bug do navaid colocalizado (corrigido):** para VOR/DME colocalizados, o bit
VOR/DME do nibble vem trocado — o ponteiro aponta para a tabela irmã. Sintoma:
uma perna de navaid resolvia a estação errada, a >800 km do aeroporto. Correção
por **âncora geográfica**: se o alvo primário cai a mais de 800 km da coordenada
do aeroporto, varre as tabelas de navaid irmãs no mesmo índice e escolhe a mais
próxima da âncora. Reduziu o resíduo de pernas distantes de 0,29% → 0,06%.

```python
def _seq_fix(self, ptr, section, anchor=None):
    nibble = section & 0x0F
    idx = ((ptr >> 5) // 16) - 1
    primary = self._read_seq_slot(nibble, idx)
    if anchor is None or nibble not in NAVAID_NIBBLES:
        return primary
    if far(primary) <= 800:               # plausível → aceita
        return primary
    # implausível → tenta tabelas de navaid irmãs no mesmo índice
    best, best_d = primary, far(primary)
    for alt_nib in NAVAID_NIBBLES - {nibble}:
        cand = self._read_seq_slot(alt_nib, idx)
        if far(cand) < best_d:
            best, best_d = cand, far(cand)
    return best
```

Detalhe: VOR/DME colocalizado grava sufixo de tipo no ident (`TGV`→`TGVC`); o
dado publicado não traz, então remove-se o sufixo `C`/`N` de idents de 4 chars.

(continua na parte 2)

---

## 6. Montagem do grafo de rotas (payload compacto)

O `html_builder._build_payload` transforma os dicts dos extractors no grafo que
o JS consome:

```
{ "n": nodes,   # [ident, lat, lon, kind, name]
  "e": edges,   # [a, b, km, airway]   (a,b = índices em n)
  "p": procs,   # { icao: [[kind, name, transition, pts], ...] }
                #   pts = [[node_id, path_term, altitude_ft, alt_desc], ...]
  "r": rwys }   # { icao: [[bearing, length_ft, elevation_ft], ...] }
```

### 6.1 Deduplicação de nós

Cada fixo/aeroporto vira um nó único, indexado por `(lat5, lon5, ident)`:

```python
def node_id(ident, lat, lon, kind, name=""):
    key = (round(lat,5), round(lon,5), ident)
    g = idx.get(key)
    if g is None:
        g = len(nodes); idx[key] = g
        nodes.append([ident, round(lat,5), round(lon,5), kind, name])
    return g
```

### 6.2 Arestas de aerovia

Cada `AirwayLeg` vira uma aresta `[u, v, km, designador]`. As duas pontas viram
nós; a distância é great-circle.

### 6.3 Conectores terminais

Aeroportos não estão na malha de aerovias. Para o roteador entrar/sair, cada
aeroporto é ligado aos **2 fixos de aerovia mais próximos** dentro de 250 km:

```python
for icao, ai in apt_ids.items():
    best = [(gc_km(la,lo, nodes[j][1],nodes[j][2]), j)
            for j in awy_nodes
            if abs(nodes[j][1]-la) <= 2.0 and abs(nodes[j][2]-lo) <= 2.5]
    best.sort()
    for km, j in best[:2]:
        if km <= 250:
            edges.append([ai, j, round(km,3), ""])   # aresta sem aerovia
```

### 6.4 Filtro por área (opcional)

`--area SB` restringe o grafo a uma caixa geográfica derivada dos aeroportos
com aquele prefixo ICAO (+3° de margem). Só afeta o HTML; os JSONs continuam
completos (mundo inteiro).

### 6.5 Compressão

O payload JSON é `gzip` nível 9 + base64, embutido no HTML como
`const PACKED="..."`. Mundial: 18 MB → 5,2 MB comprimido. Brasil (SB): 0,8 MB →
0,3 MB.

---

## 7. Otimizador — A* sobre o grafo de aerovias

O JS reconstrói a adjacência a partir de `DATA.e` e roda A* com heurística
great-circle (admissível: nunca superestima a distância restante).

```javascript
const adj = Array.from({length: NN}, () => []);
const awyOf = new Map();                       // "a,b" (a<b) → designador
for (const e of DATA.e) {
  const a=e[0], b=e[1], km=e[2], aw=e[3]||"";
  adj[a].push([b,km]); adj[b].push([a,km]);    // grafo não-direcionado
  if (aw) awyOf.set(a<b ? a+","+b : b+","+a, aw);
}

function route(src, dst) {
  if (src === dst) return {path:[src], km:0};
  const g    = new Float64Array(NN).fill(Infinity);   // custo acumulado
  const prev = new Int32Array(NN).fill(-1);           // predecessor
  const done = new Uint8Array(NN);                    // fechados
  g[src] = 0;
  const q = new Heap(); q.push([gc(src,dst), src]);   // fila por f = g + h
  while (q.size) {
    const [,u] = q.pop();
    if (done[u]) continue; done[u] = 1;
    if (u === dst) break;
    for (const [v,km] of adj[u]) {                    // relaxa vizinhos
      const nd = g[u] + km;
      if (nd < g[v]-1e-9) { g[v]=nd; prev[v]=u; q.push([nd+gc(v,dst), v]); }
    }
  }
  if (prev[dst]===-1 && src!==dst) return null;       // sem rota
  const path=[]; for (let n=dst; n!==-1; n=prev[n]) path.push(n);
  return {path: path.reverse(), km: g[dst]};
}
```

- **Heurística** `gc(v,dst)` = distância great-circle (haversine) até o destino.
- **Estruturas tipadas** (`Float64Array`, `Int32Array`, `Uint8Array`) para
  desempenho num grafo de ~140 mil nós.
- **`Heap`** é um min-heap binário por `f = g + h`.
- Complexidade prática: alguns ms mesmo no grafo mundial.

---

## 8. Montagem de rota completa — SID → en-route → STAR (ARINC 424)

Esta é a lógica que conecta os procedimentos à aerovia corretamente. Baseada na
estrutura ARINC 424, confirmada nos dados.

### 8.1 Anatomia de um procedimento

Um SID/STAR = **rota comum** ligada a:
- **Runway transition** — liga a uma cabeceira específica (fixos `RW34`,
  `CF###` — course-to-fix, só terminais, **NÃO** estão na aerovia)
- **En-route transition** — liga a um fixo da aerovia

As duas se juntam no **fixo-nome do procedimento** (ex.: `ALON1B` junta em
`ALONG`). Formalmente: `enroute_trans.last == runway_trans.first == COMMON`.

```
STAR ALON1B para SBCF, cabeceira 34, entrando por ISNEM:
  ISNEM ─(en-route trans)─ ALONG ─(runway trans)─ CF033 → AKPUV → CF039 → KUGUT
   ▲ conecta na aerovia      ▲ fixo-nome            ▲ course-to-fix p/ cabeceira
```

### 8.2 Agrupamento e montagem

O dropdown lista **uma opção por en-route transition** (qual fixo da aerovia
você entra/sai). A runway transition é escolhida automaticamente. `assembleProc`
costura no fixo comum:

```javascript
function assembleProc(opt, kind, rwyWanted) {
  const ent = opt.ent[3].map(x => x[0]);        // fixos da en-route transition
  let rwy = null;
  if (opt.rwy.length) {
    let chosen = opt.rwy.find(r => rwyMatch(r[2], rwyWanted)) || opt.rwy[0];
    rwy = chosen[3].map(x => x[0]);             // fixos da runway transition
  }
  if (kind === 'S') {                            // SID: runway → COMMON → aerovia
    return rwy ? [...rwy.slice(0,-1), ...ent] : ent;    // COMMON compartilhado
  } else {                                       // STAR: aerovia → COMMON → runway
    return rwy ? [...ent, ...rwy.slice(1)] : ent;
  }
}
```

### 8.3 Re-roteamento entre pontas

O SID **força** a saída pelo seu fixo de saída; a STAR **força** a entrada pelo
seu fixo de entrada. Então o miolo en-route é roteado **entre esses dois pontos
forçados**, não entre os aeroportos:

```javascript
function applyProcs() {
  const sidChain  = assembleProc(sOpt, 'S', null);   // [runway..COMMON..saída]
  const starChain = assembleProc(tOpt, 'T', null);   // [entrada..COMMON..runway]

  let a = current.src, b = current.dst;
  if (sidChain)  a = sidChain[sidChain.length-1];    // saída do SID
  if (starChain) b = starChain[0];                   // entrada da STAR

  let mid;
  if (current.edited) mid = extractCore(a, b);       // preserva edições (§9)
  else                mid = route(a, b).path;        // ou re-rota pela aerovia

  let path = [current.src];
  if (sidChain)  path.push(...sidChain.slice(0,-1)); // saída já vem no mid
  path.push(...mid);
  if (starChain) path.push(...starChain.slice(1));   // entrada já vem no mid
  path.push(current.dst);
  path = path.filter((v,k) => k===0 || v!==path[k-1]);   // dedup consecutivo
  // ... atualiza current.sid/star/path, redesenha
}
```

Resultado para SBKP→SBCF (ALON1B): `SBKP → [aerovia] → ISNEM → ALONG → CF033 →
AKPUV → CF039 → KUGUT → SBCF` — traço único e contínuo.

---

## 9. Edição manual da rota + persistência

### 9.1 Modelo de estado

```javascript
current = {
  path,            // array de node ids (rota completa atual)
  base,            // cópia da rota original (para reset)
  dct:  new Set(), // legKey(a,b) das pernas forçadas a DCT (linha reta)
  edited: false,   // usuário editou manualmente?
  sid, star,       // cadeias de procedimento desenhadas
  src, dst         // aeroportos
}
```

### 9.2 Cenário 1 — inserir/editar fixos (campo livre)

Cada "Para" da tabela é um `<input>`. `resolveIdent` mapeia o texto para o nó
mais próximo (desambigua idents repetidos pela distância a um nó de referência):

```javascript
function resolveIdent(str, refId) {
  const cands = byName.get(str.trim().toUpperCase());
  if (!cands) return null;
  if (cands.length === 1 || refId == null) return cands[0];
  let best = cands[0], bd = Infinity;               // escolhe o mais próximo
  for (const c of cands) { const d = gc(c, refId); if (d < bd) { bd=d; best=c; } }
  return best;
}
```

Botões `+` (inserir fixo depois) e `×` (remover) editam `current.path`.
`rebuild()` recalcula km/estatísticas/mapa **sem re-rotear** (preserva o que o
usuário montou).

### 9.3 Cenário 2 — trocar aerovia por DCT

Cada linha da tabela é uma aresta única de aerovia (fixos adjacentes). Clicar na
célula da aerovia alterna a perna entre o designador e **DCT** (`current.dct`).
Em DCT a perna é linha reta, não busca aerovia; desenhada tracejada. O ganho
real aparece ao **deletar** fixos intermediários que faziam a aerovia dar o bico
— a perna resultante fica reta e mais curta.

```javascript
function legKey(a,b){ return a<b ? a+"_"+b : b+"_"+a; }
function isDct(a,b){ return current.dct.has(legKey(a,b)); }
// toggle: if (dct.has(key)) dct.delete(key); else dct.add(key);
```

### 9.4 Persistência ao trocar SID/STAR

`extractCore(a,b)` preserva o miolo en-route editado entre a saída do SID e a
entrada da STAR, para que trocar procedimento **não apague** as edições. Só
"Calcular rota" zera tudo.

```javascript
function extractCore(a, b) {
  const p = current.path;
  let i = p.indexOf(a), j = p.lastIndexOf(b);
  if (i<0 || j<0 || i>j) {                 // pontas mudaram: usa miolo sem SID/STAR
    const s = current.sid  ? current.sid.length-1        : 1;
    const e = current.star ? p.length-current.star.length : p.length-1;
    return p.slice(Math.max(1,s), Math.max(1,e));
  }
  return p.slice(i, j+1);
}
```

### 9.5 Toggle de nomes no mapa

Botão `#lbl-toggle` (`showAllLabels`). Quando ligado e `zoom>=7`, o `paint()`
desenha rótulos de todos os waypoints visíveis (não só os da rota), com
supressão de sobreposição, para identificar fixos e digitá-los na edição.

---

## 10. Coluna de aerovia e restrição de altitude na tabela

- **Aerovia por perna:** `legAirway(a,b)` consulta `awyOf`. Em DCT, mostra
  "DCT". Coluna antes da distância.
- **Restrição de altitude:** `ALT` (Map nodeId→{alt,desc}) é preenchido de
  `collectAlt` a partir dos pontos do SID/STAR selecionados. Formatação:

```javascript
function fmtAlt(id) {
  const r = ALT.get(id); if (!r || !r.alt) return '';
  const a = r.alt.toLocaleString('pt-BR');
  if (r.desc === '+') return '≥'+a;    // no ou acima
  if (r.desc === '-') return '≤'+a;    // no ou abaixo
  if (r.desc === 'B') return '~'+a;    // janela (limite principal)
  return a;                            // exata
}
```

Exemplo (STAR ALON1B): ALONG ≤24000, CF033 ≤13000, AKPUV ≥11000, CF039 ≥9000,
KUGUT ≥7000 — o perfil de descida real.


---

## 11. Status completo de decodificação

### 11.1 Validado 100% (contra CSV oficial)

| Parâmetro | Como | Validação |
|-----------|------|-----------|
| Waypoints en-route/terminais | tabela rs=16, lat/lon padrão | 100% |
| Aeroportos | rs=40 | 100% |
| Pistas (proa, comprimento, elevação) | rs=20 | 100% |
| SID/STAR/APPR: sequência de fixos | headers rs=20 + seq rs=24 | 100% |
| Path & Termination | byte 0 → PATH_TERM | 100% |
| Altitude (valor) | bytes 1-2 | 100% |
| **Descritor de altitude** (+/-/''/B) | byte 3 bits 4-5 | 288448/288448 |
| **Speed Limit** | índice em tabela ARINC de 47 entradas, 6 bits baixos de `u16be(sr[16:18])` | 99,15% |
| **Aerovia: designador + delimitação** | AIRWAY.S01 `(ptr>>7)-1` | 91,5% dos pares vs CSV |
| **Airway Level (H/L/B)** | 2 bits baixos da palavra de nome em AIRWAY.S01: `{0:H,1:L,2:B}` | 5468/5468 |

> **Speed Limit — detalhe do slot compartilhado:** quando o descritor é `B`
> (janela), `sr[16:18]` guarda o 2º limite de altitude em vez da velocidade —
> então a velocidade só é válida em pernas não-B.

### 11.2 Decodificado, ainda NÃO ligado no reader

- **Speed Limit** e **Airway Level (H/L/B)**: decodificados e validados, mas
  ainda não plugados no `reader.py`/payload. Para ligar Level: ao ler
  `AIRWAY.S01`, `level = {0:'H',1:'L',2:'B'}[name_word & 3]`.

### 11.3 Parcial / não resolvido a contento

- **FAS.S01 (aproximações LPV/SBAS):** 52-byte, 4507 registros. Decodificado e
  validado: Glide Path Angle em `+36 w2 LE /100` (4473/4473), CRC em `+42 w4`,
  header de 10 bytes. **Não resolvido:** coordenadas LTP/FPAP — a latitude
  correlaciona r=1.0 em `+18 LE 4-byte` na escala ~0.0005″, mas tem resíduo
  teimoso de ~12″/~370 m + offset constante que não sai por bit-masking;
  longitude não está em nenhum campo byte-alinhado. Confirmado que NÃO é
  desalinhamento de ciclo (testado no 2606 casado). Precisa da spec de bits do
  FAS Data Block da Thales. **Não exportado** (370 m é grosseiro demais para
  threshold de aproximação de precisão).
- **ILS.S01:** rs=32, 2816 registros. Ident do localizer + coords validados
  (141/141 a <8 km do aeroporto). Frequência/proa/glideslope **não** confirmados
  (sem CSV de navaid para validar).
- **Navaids (VOR/DME/NDB):** tabelas decodificam estruturalmente (tamanhos
  corretos: VOR rs=28, DME rs=32, VOR_DMEC rs=32, VOR_DMEN rs=20, NDB rs=28) mas
  frequência/classe/variação **não** validáveis sem export da seção D.
- **Magnetic Course / Theta:** armazenados mas em codificação não-linear
  (resistiu a byte-corr, variância máx 3,9%, bitstream). Só 24% batem com a proa
  geométrica calculada. Cosmético.
- **2º limite da janela "B":** localizado no slot compartilhado byte 16-17, mas
  encoding de índice segmentado não-linear (raw 55-61→10000ft, 67→10500...).
  Não fechado; marginal (3804 pernas).
- **FIX_INFO.S01:** estrutura de ponteiros (8-byte, sentinela `0xd0000000`)
  resolve para waypoints, semântica não validada.
- **ALT_INFO.S01:** NÃO é restrição de altitude — é tabela de ponteiros/índice
  (326 entradas), infraestrutura. Descartado.

### 11.4 Limite-chave de validação

Os exports FULL (2606/2607) só contêm CSVs de waypoint/aeroporto/pista/
procedimento/pathpoint(+aerovias) — **nenhum** de navaid (seção D)/ILS/FIX_INFO.
Por isso essas tabelas decodificam estruturalmente mas não fecham 100%. Os
exports de maior valor pendentes: **seção D (navaids)**, depois **ILS**.

---

## 12. Metodologia de bit-scan (como campos empacotados foram quebrados)

Para campos bit-packed no registro de 24 bytes (velocidade, descritor,
2º limite), a técnica que funcionou:

1. **`align.py`** constrói `pairs.pkl`: alinha 448.571 pernas de procedimento
   do binário às linhas correspondentes do CSV (por CRC/ordem), criando pares
   (registro binário ↔ valores-verdade do CSV).
2. **Bit-scan por ganho de informação / variância:** para cada bit (ou janela de
   bits) do registro, mede quanto ele explica da variância do campo-alvo. Bits
   com alto ganho revelam onde o campo está.
3. **Refinamento:** window + shift + mask para achar a fatia exata; teste de
   correlação/exatidão contra o CSV.

Isso decodificou o descritor de altitude (100%) e o speed limit (99%). Falhou em
course (não-linear) e nas coordenadas FAS (bit-packed sub-arcsec).

---

## 13. O pacote `fmsnav_export` (estrutura e reuso)

```
fmsnav_export/
  __init__.py        API pública: FmsDatabase, build
  __main__.py        CLI (python -m fmsnav_export)
  reader.py          decoder .S01 → objetos (o núcleo validado)
  extractors.py      um extrator por parâmetro; dict EXTRACTORS
  json_export.py     grava um JSON por parâmetro em out/db/
  html_builder.py    monta payload {n,e,p,r} → injeta em templates/planner.html
  build.py           orquestra reader → json_export → html_builder
  templates/
    planner.html     shell do planejador (UI + Leaflet + A* + montagem/edição)
                     com placeholders __PACKED__ e __CYCLE__
  README.md
```

### 13.1 Uso

```bash
python -m fmsnav_export CICLO.zip --cycle 2607 --out ./out          # mundo
python -m fmsnav_export CICLO.zip --cycle 2607 --area SB --out ./out # Brasil
```

```python
from fmsnav_export import build
build("CICLO.zip", out="./out", cycle="2607", area=["SB"])
```

### 13.2 Saída

```
out/
  planejador.html
  db/
    index.json     airports.json  runways.json   waypoints.json
    airways.json   sids.json      stars.json     approaches.json
```

Cada JSON: `{"parameter": <nome>, "cycle": <ciclo>, "count": <n>, "data": <...>}`.

### 13.3 Estender — adicionar um parâmetro novo

1. Escreva `extract_<param>(db) -> list|dict` em `extractors.py`.
2. Registre em `EXTRACTORS = { ..., "<param>": extract_<param> }`.
3. Pronto: vira `out/db/<param>.json` automaticamente. Se for pra entrar no
   grafo do HTML, consuma o dict em `html_builder._build_payload`.

### 13.4 Contrato de dados (formatos exatos)

```
airports.json   : [ {icao, lat, lon}, ... ]
runways.json    : { icao: [ {ident, bearing, length_ft, elevation_ft}, ... ] }
waypoints.json  : [ {ident, lat, lon, kind}, ... ]                  kind: W|P
airways.json    : [ {airway, from, from_lat, from_lon, to, to_lat, to_lon, km}, ... ]
sids/stars/
  approaches.json: { icao: [ {name, transition,
                              points:[ {ident,lat,lon,path_term,
                                        altitude_ft,alt_desc}, ...]}, ...] }
```

`alt_desc` ∈ `{'+','-','','B'}`. Payload do HTML: `{n,e,p,r}` (ver §6).

---

## 14. Notas de reuso para o Claude (sessões futuras)

Se você (Claude) retomar este projeto:

- **O decoder validado é `fmsnav_export/reader.py`** (idêntico ao `fmsnav/`
  original). É a fonte da verdade. Não reintroduza a escala errada de ponteiro
  de aerovia — é `(ptr>>7)-1`, calibrada com erro zero.
- **Bugs já resolvidos (não repita):** navaid colocalizado (bit VOR/DME trocado,
  corrigido por âncora geográfica); DCT falso de aerovia (fronteiras via
  AIRWAY.S01 + guarda 300 km); SID/STAR desconectados (montagem ARINC 424 por
  fixo comum + re-roteamento entre pontas).
- **O que dá retorno se houver novos exports:** seção D (navaids → frequências)
  e ILS. Ambos já decodificam estruturalmente; falta só o gabarito p/ validar.
  É só escrever um extrator novo.
- **O que está decodificado mas não ligado:** Speed Limit e Airway Level (H/L/B).
  Plugar é trivial (fórmulas em §11).
- **Problemas ainda abertos:** coordenadas FAS de precisão (bit-packed
  sub-arcsec, precisa da spec Thales), magnetic course (não-linear), 2º limite
  da janela B (índice segmentado).
- **Método para campos bit-packed:** `align.py` → `pairs.pkl` → bit-scan por
  variância/ganho de informação vs CSV (§12).
- **Validação:** os CSVs FULL (2606/2607) são o gabarito; cobrem waypoint/
  aeroporto/pista/procedimento/pathpoint/aerovias — não cobrem navaid/ILS.
- **O planejador HTML** tem toda a lógica no `templates/planner.html`; o
  `html_builder` só injeta payload+ciclo. Features: A*, montagem SID/STAR,
  edição de rota (campo livre, inserir/remover), DCT por perna, coluna de
  aerovia, restrição de altitude, toggle de nomes.

### 14.1 Glossário rápido

- **AIRAC** — ciclo de atualização de dados aeronáuticos (28 dias).
- **SID** — saída padrão por instrumentos. **STAR** — chegada padrão.
- **En-route / runway transition** — trechos que ligam o procedimento à aerovia
  e à cabeceira, respectivamente; unidos no fixo-nome.
- **Path & Termination (ARINC 424)** — como uma perna é voada (TF=track-to-fix,
  CF=course-to-fix, DF=direct-to-fix, etc.).
- **DCT** — direto (linha reta entre dois fixos, sem aerovia).
- **LTP/FPAP** — pontos de referência de aproximação de precisão (SBAS/LPV).
- **great-circle / haversine** — distância sobre a esfera; heurística do A*.

---

## 15. Resumo de um parágrafo

O banco FMS Thales é um conjunto de tabelas binárias de registros fixos que se
referenciam por ponteiros escalados. Texto é 6 bits/char num uint32; coordenadas
são uint24 com escala fixa; ponteiros usam duas escalas conforme o contexto.
Waypoints, aeroportos, pistas e a sequência de procedimentos decodificam e
validam 100%; aerovias exigiram calibrar a escala do ponteiro de `AIRWAY.S01`
(`(ptr>>7)-1`) e delimitar por ordem de arquivo + guarda de 300 km; navaids de
procedimento exigiram corrigir o bit VOR/DME trocado por âncora geográfica.
Restrição de altitude (descritor +/-/''/B), speed limit e airway level foram
quebrados por bit-scan contra o CSV. O grafo de rotas junta arestas de aerovia
(com designador) e conectores terminais; o A* com heurística great-circle acha a
rota; SID/STAR se conectam pela estrutura ARINC 424 (en-route + runway
transition unidas no fixo comum), com re-roteamento entre as pontas forçadas. O
planejador HTML permite editar a rota em campo livre, alternar aerovia↔DCT, e
exibe aerovia e restrição de altitude por perna. Tudo empacotado em
`fmsnav_export`, que recebe só o zip e gera os JSONs (um por parâmetro) e o HTML.
