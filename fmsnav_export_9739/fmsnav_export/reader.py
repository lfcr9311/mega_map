"""Leitor do Navigation Database FMS (Thales) — formato binario proprietario.

Le exclusivamente os arquivos .S01 de dentro do zip do ciclo AIRAC. Nao usa
nenhum export CSV: todo o conteudo vem do binario.

Formato decodificado por engenharia reversa e validado contra os ciclos 2606 e
2607 (ver FORMATO.md). Resumo das regras:

  texto      simbolos de 6 bits, deslocamentos 26/20/14/8/2 num uint32 BE;
             digitos nos codigos 14-23, letras em 30-55, hifen em 11.
             Nomes de 6 caracteres levam o sexto nos bits 32-37.
  latitude   uint24 BE / 80000 graus, complemento acima de 90
  longitude  uint24 BE / 40000 graus, complemento acima de 180
  ponteiros  AWY_SEQ:        indice = (offset // 32) - 1
             sequencias:     indice = ((ponteiro >> 5) // 16) - 1
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------- texto

CHARS: dict[int, str] = {0: "", 11: "-"}
CHARS.update({14 + i: str(i) for i in range(10)})
CHARS.update({30 + i: chr(65 + i) for i in range(26)})

_SHIFTS = (26, 20, 14, 8, 2)


def decode_ident(v: int) -> str:
    """uint32 -> identificador de ate 5 caracteres."""
    return "".join(CHARS.get((v >> s) & 0x3F, "?") for s in _SHIFTS).strip()


def decode_name6(rec: bytes) -> str:
    """Nome de procedimento: 5 chars em +0..3 e o sexto nos bits 32..37."""
    head = decode_ident(int.from_bytes(rec[0:4], "big"))
    sixth = CHARS.get((int.from_bytes(rec[0:8], "big") >> (64 - 38)) & 0x3F, "")
    return (head + sixth).strip()


# ------------------------------------------------------------ coordenadas

def decode_lat(rec: bytes, off: int) -> float:
    v = int.from_bytes(rec[off:off + 3], "big") / 80000.0
    return v - 2 ** 24 / 80000.0 if v > 90 else v


def decode_lon(rec: bytes, off: int) -> float:
    v = int.from_bytes(rec[off:off + 3], "big") / 40000.0
    return v - 2 ** 24 / 40000.0 if v > 180 else v


# -------------------------------------------------------------- modelo

@dataclass(frozen=True, slots=True)
class Fix:
    ident: str
    lat: float
    lon: float
    kind: str          # WPT_ENRT, WPT_TERM, VOR_DME, NDB, DME, VOR, AIRPORT

    def __repr__(self) -> str:
        return f"{self.ident}({self.lat:.4f},{self.lon:.4f})"


@dataclass(frozen=True, slots=True)
class Airport:
    icao: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Runway:
    airport_idx: int
    lat: float
    lon: float
    bearing: float | None      # graus magneticos
    length_ft: int             # pes
    elevation_ft: int          # pes


@dataclass(frozen=True, slots=True)
class Leg:
    """Uma perna de procedimento (SID, STAR ou aproximacao)."""

    seq: int
    path_term: str             # TF, CF, DF, CA, VI, ...
    fix: Fix | None
    altitude_ft: int | None
    alt_desc: str              # '+' (ou acima), '-' (ou abaixo), '' (exata), 'B' (janela)
    distance_nm: float | None
    rnp: float | None

    @property
    def has_position(self) -> bool:
        return self.fix is not None


@dataclass(frozen=True, slots=True)
class Procedure:
    kind: str                  # SID, STAR, APPR
    airport: str
    name: str
    transition: str
    legs: tuple[Leg, ...]

    @property
    def fixes(self) -> tuple[Fix, ...]:
        return tuple(l.fix for l in self.legs if l.fix is not None)


@dataclass(frozen=True, slots=True)
class AirwayLeg:
    airway: str
    frm: Fix
    to: Fix


# Path & Termination: o codigo do byte +0 mapeia para o tipo ARINC 424.
PATH_TERM: dict[int, str] = {
    0: "AF", 2: "AF", 6: "AF", 10: "CA", 14: "CA", 16: "CD", 18: "CD", 22: "CD",
    24: "CF", 26: "CF", 30: "CF", 32: "CI", 34: "CI", 38: "CI", 40: "CR",
    42: "CR", 46: "CR", 48: "DF", 50: "DF", 54: "DF", 58: "FA", 62: "FA",
    64: "FD", 66: "FD", 70: "FD", 72: "FC", 74: "FC", 78: "FC", 80: "FM",
    82: "FM", 86: "FM", 90: "HA", 94: "HA", 96: "HF", 98: "HF", 102: "HF",
    104: "HM", 106: "HM", 110: "HM", 112: "IF", 114: "IF", 118: "IF",
    122: "PI", 128: "RF", 130: "RF", 134: "RF", 136: "TF", 138: "TF",
    139: "TF", 142: "TF", 146: "VA", 150: "VA", 152: "VD", 154: "VD",
    160: "VI", 162: "VI", 166: "VI", 168: "VM", 170: "VM", 174: "VM",
    176: "VR", 178: "VR",
}

# tabela -> (nome do arquivo, tamanho do registro, offset lat, offset lon)
FIX_TABLES: dict[int, tuple[str, int, int, int]] = {
    0x20: ("WPT_ENRT.S01", 16, 8, 12),
    0x90: ("VOR_DMEC.S01", 32, 4, 8),
    0xB0: ("NDB_ENRT.S01", 28, 4, 8),
    0x80: ("VOR.S01", 28, 4, 8),
    0x70: ("DME.S01", 32, 4, 8),
    0xA0: ("VOR_DMEN.S01", 20, 4, 8),
}

KIND_OF = {
    0x20: "WPT_ENRT", 0x90: "VOR_DME", 0xB0: "NDB",
    0x80: "VOR", 0x70: "DME", 0xA0: "VOR_DME",
}

# Nas sequencias de procedimento, o nibble baixo do byte +3 diz em QUAL tabela
# o ponteiro deve ser resolvido. Sem isso um mesmo indice resolve tanto em
# WPT_TERM quanto em WPT_ENRT e o fixo sai no pais errado.
SECTION_TABLE: dict[int, tuple[str, int]] = {
    0x0: ("AIRPORT.S01", 40),     # P/A — aerodromo
    0x1: ("RUNWAY.S01", 20),      # P/G — cabeceira
    0x2: ("WPT_ENRT.S01", 16),    # E/A — waypoint en-route
    0x3: ("WPT_TERM.S01", 16),    # P/C — waypoint terminal
    0x7: ("VOR.S01", 28),         # D   — VOR
    0x8: ("DME.S01", 32),         # D   — DME
    0x9: ("VOR_DMEC.S01", 32),    # D   — VOR/DME
    0xA: ("VOR_DMEN.S01", 20),    # D   — VOR/DME nao colocalizado
    0xB: ("NDB_ENRT.S01", 28),    # D/B — NDB
    0xC: ("NDB_TERM.S01", 16),    # P/N — NDB terminal
}

SECTION_KIND = {
    0x0: "AIRPORT", 0x1: "RUNWAY", 0x2: "WPT_ENRT", 0x3: "WPT_TERM",
    0x7: "VOR", 0x8: "DME", 0x9: "VOR_DME", 0xA: "VOR_DME",
    0xB: "NDB", 0xC: "NDB",
}

# Nibbles cujo alvo e um navaid. Para pernas de procedimento que referenciam
# navaid (tipico DF/CF para VOR/DME), o bit VOR/DME do nibble vem trocado para
# estacoes colocalizadas: ~92% das pernas "distantes" resolvem corretamente na
# tabela irma no MESMO indice. Sem um sinal local confiavel, corrige-se por
# consistencia geografica com o aerodromo (ver _seq_fix, parametro anchor).
NAVAID_NIBBLES = frozenset({0x7, 0x8, 0x9, 0xA, 0xB, 0xC})


# --------------------------------------------------------------- leitor

class FmsDatabase:
    """Banco de navegacao FMS carregado de um zip de ciclo AIRAC."""

    def __init__(self, source: str | Path):
        self.source = Path(source)
        self._raw: dict[str, bytes] = {}
        self._load_files()

        # tabelas de fixos, indexadas por posicao no arquivo
        self.enroute: list[Fix] = self._read_fix_table(0x20)
        self.terminal: list[Fix] = self._read_terminal()
        self.airports: list[Airport] = self._read_airports()
        self._apt_by_icao = {a.icao: i for i, a in enumerate(self.airports)}
        self.runways: list[Runway] = self._read_runways()

        self._fix_cache: dict[int, list[Fix]] = {}

    # ------------------------------------------------------------ zip

    def _load_files(self) -> None:
        needed = {
            "WPT_ENRT.S01", "WPT_TERM.S01", "AIRPORT.S01", "RUNWAY.S01",
            "VOR.S01", "VOR_DMEC.S01", "VOR_DMEN.S01", "NDB_ENRT.S01",
            "NDB_TERM.S01", "DME.S01", "ILS_DMEN.S01",
            "AWY_SEQ.S01", "AIRWAY.S01", "LK_FX_AW.S01",
            "SID.S01", "STAR.S01", "APPR.S01",
            "SID_SEQ.S01", "STAR_SEQ.S01", "APPR_SEQ.S01",
            "ARPT_SID.S01", "ARPT_STA.S01", "ARPT_APP.S01",
            "STANDARD.HD",
        }
        if self.source.is_dir():
            for name in needed:
                for p in self.source.rglob(name):
                    self._raw[name] = p.read_bytes()
                    break
        else:
            with zipfile.ZipFile(self.source) as z:
                for info in z.infolist():
                    base = Path(info.filename).name
                    if base in needed:
                        self._raw[base] = z.read(info)
        missing = needed - set(self._raw) - {"LK_FX_AW.S01", "AIRWAY.S01", "STANDARD.HD"}
        if missing:
            raise ValueError(f"tabelas ausentes no banco: {sorted(missing)}")

    def _buf(self, name: str) -> bytes:
        return self._raw.get(name, b"")

    # --------------------------------------------------------- tabelas

    def _read_fix_table(self, code: int) -> list[Fix]:
        name, rs, clat, clon = FIX_TABLES[code]
        buf = self._buf(name)
        kind = KIND_OF[code]
        out = []
        for i in range(len(buf) // rs):
            rec = buf[i * rs:(i + 1) * rs]
            out.append(Fix(decode_ident(int.from_bytes(rec[:4], "big")),
                           decode_lat(rec, clat), decode_lon(rec, clon), kind))
        return out

    def _read_terminal(self) -> list[Fix]:
        buf = self._buf("WPT_TERM.S01")
        return [
            Fix(decode_ident(int.from_bytes(buf[i * 16:i * 16 + 4], "big")),
                decode_lat(buf[i * 16:(i + 1) * 16], 4),
                decode_lon(buf[i * 16:(i + 1) * 16], 8),
                "WPT_TERM")
            for i in range(len(buf) // 16)
        ]

    def _read_airports(self) -> list[Airport]:
        buf = self._buf("AIRPORT.S01")
        return [
            Airport(decode_ident(int.from_bytes(buf[i * 40:i * 40 + 4], "big")),
                    decode_lat(buf[i * 40:(i + 1) * 40], 4),
                    decode_lon(buf[i * 40:(i + 1) * 40], 8))
            for i in range(len(buf) // 40)
        ]

    def _read_runways(self) -> list[Runway]:
        buf = self._buf("RUNWAY.S01")
        out = []
        for i in range(len(buf) // 20):
            r = buf[i * 20:(i + 1) * 20]
            brg = int.from_bytes(r[12:14], "big") / 160.0
            elev_raw = int.from_bytes(r[14:16], "big")
            elev = (elev_raw - 65536) / 4 if elev_raw > 60000 else elev_raw / 4
            out.append(Runway(
                airport_idx=int.from_bytes(r[0:4], "big"),
                lat=decode_lat(r, 4), lon=decode_lon(r, 8),
                bearing=brg if brg <= 360 else None,
                length_ft=int.from_bytes(r[16:18], "big") * 2,
                elevation_ft=int(round(elev)),
            ))
        return out

    # -------------------------------------------------------- ponteiros

    def _airway_fix(self, ptr: int) -> Fix | None:
        """AWY_SEQ: [codigo de tabela : 8 | offset : 24], indice = offset//32 - 1."""
        code = ptr >> 24
        idx = (ptr & 0xFFFFFF) // 32 - 1
        if code not in FIX_TABLES or idx < 0:
            return None
        table = self._fix_cache.get(code)
        if table is None:
            table = self._read_fix_table(code)
            self._fix_cache[code] = table
        return table[idx] if idx < len(table) else None

    def _read_seq_slot(self, nibble: int, idx: int) -> Fix | None:
        """Le um registro de fixo pela tabela do nibble no indice dado.

        Retorna None se a tabela nao existe, o indice esta fora ou o ident e
        vazio. Nao aplica correcao de navaid — e o tijolo usado por _seq_fix.
        """
        entry = SECTION_TABLE.get(nibble)
        if entry is None or idx < 0:
            return None
        name, size = entry
        buf = self._buf(name)
        if (idx + 1) * size > len(buf):
            return None
        rec = buf[idx * size:(idx + 1) * size]
        if name == "RUNWAY.S01":
            brg = int.from_bytes(rec[12:14], "big") / 160.0
            num = int(round(brg / 10)) or 36
            return Fix(f"RW{num:02d}", decode_lat(rec, 4),
                       decode_lon(rec, 8), "RUNWAY")
        clat, clon = (8, 12) if name == "WPT_ENRT.S01" else (4, 8)
        ident = decode_ident(int.from_bytes(rec[:4], "big"))
        if not ident:
            return None
        kind = SECTION_KIND.get(nibble, "FIX")
        # VOR/DME colocalizado grava o sufixo de tipo no ident (TGV -> TGVC);
        # o dado publicado nao o traz
        if kind == "VOR_DME" and len(ident) == 4 and ident[-1] in "CN":
            ident = ident[:-1]
        return Fix(ident, decode_lat(rec, clat), decode_lon(rec, clon), kind)

    def _seq_fix(self, ptr: int, section: int,
                 anchor: tuple[float, float] | None = None) -> Fix | None:
        """Sequencia de procedimento: indice = ((ptr >> 5)//16) - 1.

        A tabela de destino vem do nibble baixo do byte +3 do registro; o
        ponteiro sozinho e ambiguo entre WPT_TERM e WPT_ENRT.

        Para pernas de navaid, o bit VOR/DME do nibble pode vir trocado em
        estacoes colocalizadas. Quando `anchor` (coord do aerodromo) e dado e
        o alvo primario cai a mais de 800 km dele, tenta-se as tabelas de
        navaid irmas no mesmo indice e escolhe-se a mais proxima do anchor.
        """
        nibble = section & 0x0F
        idx = ((ptr >> 5) // 16) - 1
        primary = self._read_seq_slot(nibble, idx)

        if anchor is None or nibble not in NAVAID_NIBBLES:
            return primary

        def far(fix: Fix | None) -> float:
            if fix is None:
                return float("inf")
            from math import radians, sin, cos, asin, sqrt
            p1, p2 = radians(anchor[0]), radians(fix.lat)
            dp = radians(fix.lat - anchor[0])
            dl = radians(fix.lon - anchor[1])
            h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
            return 2 * 6371.0088 * asin(sqrt(h))

        best = primary
        best_d = far(primary)
        if best_d <= 800:
            return best
        # o alvo primario e implausivel: varre as demais tabelas de navaid
        # no mesmo indice e fica com a mais proxima do aerodromo
        for alt_nib in NAVAID_NIBBLES:
            if alt_nib == nibble:
                continue
            cand = self._read_seq_slot(alt_nib, idx)
            d = far(cand)
            if d < best_d:
                best, best_d = cand, d
        return best

    # -------------------------------------------------------- aerovias

    def airways(self) -> Iterator[AirwayLeg]:
        """Pernas de aerovia, delimitadas por AIRWAY.S01.

        AIRWAY.S01 (rs=8) = [nome:4][ponteiro:4]. Cada registro marca o inicio
        de uma corrida de fixos em AWY_SEQ; o indice inicial e (ptr >> 5) - 4.
        Os registros estao em ordem crescente de inicio no arquivo, entao o fim
        de cada corrida e o inicio do PROXIMO registro (na ordem do arquivo, nao
        por nome). Um mesmo designador pode aparecer em varios registros
        consecutivos (sub-segmentos regionais de "M725", p.ex.) — cada um e uma
        corrida propria, o que evita ligar fixos de regioes diferentes. Assim
        cada perna sai contigua e correta, e carrega o designador da aerovia.

        Validado: A14 reproduz exatamente os 15 fixos do CSV ER. Sem AIRWAY.S01,
        cai num heuristico de salto conservador (<300 km).
        """
        buf = self._buf("AWY_SEQ.S01")
        n_seq = len(buf) // 8
        awy = self._buf("AIRWAY.S01")

        if not awy:
            prev: Fix | None = None
            for i in range(n_seq):
                fix = self._airway_fix(struct.unpack_from(">I", buf, i * 8)[0])
                if fix is not None and prev is not None and _haversine(prev, fix) < 300:
                    yield AirwayLeg("", prev, fix)
                prev = fix
            return

        recs = []
        for i in range(len(awy) // 8):
            name = decode_ident(int.from_bytes(awy[i * 8:i * 8 + 4], "big"))
            # indice inicial em AWY_SEQ: start = ptr/128 - 1 (calibrado vs CSV ER,
            # erro zero em todas as aerovias). Os registros ja vem em ordem
            # crescente de start no arquivo, particionando AWY_SEQ sem buracos.
            start = (int.from_bytes(awy[i * 8 + 4:i * 8 + 8], "big") >> 7) - 1
            recs.append((name, start))

        # A fatia do AIRWAY.S01 da o DESIGNADOR e o agrupamento certo, mas dentro
        # de uma corrida ainda aparecem saltos falsos (fixos nao sao todos
        # sequenciais). Aplica-se um limiar de salto para nao ligar fixos
        # distantes: assim cada perna sai com o designador correto E sem DCT
        # falso (ex.: DIDAB->NIPDA 558 km fica de fora). 300 km cobre qualquer
        # perna continental real.
        for k, (name, start) in enumerate(recs):
            end = recs[k + 1][1] if k + 1 < len(recs) else n_seq
            if not (0 <= start < end <= n_seq):
                continue
            prev = None
            for i in range(start, end):
                fix = self._airway_fix(struct.unpack_from(">I", buf, i * 8)[0])
                if fix is not None and prev is not None:
                    if _haversine(prev, fix) < 300:
                        yield AirwayLeg(name, prev, fix)
                prev = fix

    # --------------------------------------------------- procedimentos

    def _procedures(self, kind: str) -> Iterator[Procedure]:
        link_f, hdr_f, seq_f = {
            "SID": ("ARPT_SID.S01", "SID.S01", "SID_SEQ.S01"),
            "STAR": ("ARPT_STA.S01", "STAR.S01", "STAR_SEQ.S01"),
            "APPR": ("ARPT_APP.S01", "APPR.S01", "APPR_SEQ.S01"),
        }[kind]
        link, hdr, seq = self._buf(link_f), self._buf(hdr_f), self._buf(seq_f)
        n_seq = len(seq) // 24

        # ponteiro -> primeira linha; o fim e o inicio do proximo procedimento
        starts: list[tuple[int, int, int]] = []   # (apt_idx, hdr_idx, first)
        for i in range(len(link) // 8):
            a, b = struct.unpack_from(">II", link, i * 8)
            h = b - 1
            if h * 20 + 20 > len(hdr):
                continue
            rec = hdr[h * 20:h * 20 + 20]
            first = (int.from_bytes(rec[8:12], "big") >> 7) - 1
            starts.append((a - 1, h, first))
        bounds = sorted({s[2] for s in starts if 0 <= s[2] < n_seq})
        nxt = {v: (bounds[i + 1] if i + 1 < len(bounds) else n_seq)
               for i, v in enumerate(bounds)}

        for apt_idx, h, first in starts:
            if not (0 <= apt_idx < len(self.airports)) or first < 0:
                continue
            rec = hdr[h * 20:h * 20 + 20]
            apt = self.airports[apt_idx]
            anchor = (apt.lat, apt.lon)
            legs = []
            for j in range(first, nxt.get(first, n_seq)):
                sr = seq[j * 24:(j + 1) * 24]
                if len(sr) < 24:
                    break
                alt = int.from_bytes(sr[1:3], "big")
                dist = int.from_bytes(sr[14:16], "big") // 16
                # descritor de altitude: bits 4-5 do byte 3 (validado 100% vs CSV)
                alt_desc = {0: "+", 1: "-", 2: "", 3: "B"}[(sr[3] >> 4) & 3]
                legs.append(Leg(
                    seq=j - first + 1,
                    path_term=PATH_TERM.get(sr[0], "??"),
                    fix=self._seq_fix(int.from_bytes(sr[4:8], "big"), sr[3],
                                      anchor),
                    altitude_ft=alt or None,
                    alt_desc=alt_desc if alt else "",
                    distance_nm=float(dist) if dist else None,
                    rnp=sr[12] * 5 / 100 if sr[12] else None,
                ))
            yield Procedure(kind, self.airports[apt_idx].icao, decode_name6(rec),
                            decode_ident(int.from_bytes(rec[12:16], "big")),
                            tuple(legs))

    def sids(self) -> Iterator[Procedure]:
        return self._procedures("SID")

    def stars(self) -> Iterator[Procedure]:
        return self._procedures("STAR")

    def approaches(self) -> Iterator[Procedure]:
        return self._procedures("APPR")

    # ------------------------------------------------------------ util

    def airport(self, icao: str) -> Airport | None:
        i = self._apt_by_icao.get(icao.upper())
        return self.airports[i] if i is not None else None

    def runways_of(self, icao: str) -> list[Runway]:
        i = self._apt_by_icao.get(icao.upper())
        if i is None:
            return []
        # o campo +0 da pista referencia o aeroporto; casamos por proximidade
        a = self.airports[i]
        return [r for r in self.runways
                if abs(r.lat - a.lat) < 0.15 and abs(r.lon - a.lon) < 0.15]

    def summary(self) -> str:
        return (f"{len(self.enroute):,} fixos en-route | "
                f"{len(self.terminal):,} terminais | "
                f"{len(self.airports):,} aerodromos | "
                f"{len(self.runways):,} pistas")


def _haversine(a: Fix, b: Fix) -> float:
    from math import radians, sin, cos, asin, sqrt
    p1, p2 = radians(a.lat), radians(b.lat)
    dp, dl = radians(b.lat - a.lat), radians(b.lon - a.lon)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))
