"""Leitor do Navigation Database FMS (Thales) — formato binario proprietario.

Le exclusivamente os arquivos .S01 de dentro do zip do ciclo AIRAC (ou de um
diretorio). Nao usa nenhum export CSV: todo o conteudo vem do binario.

Ponteiros (dois esquemas de escala — confundi-los foi fonte de bug):
  AWY_SEQ:     [codigo de tabela : 8 | offset : 24], indice = offset//32 - 1
  sequencias:  indice = ((ponteiro >> 5) // 16) - 1
  AIRWAY.S01:  inicio da corrida em AWY_SEQ = (ptr >> 7) - 1
"""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path
from typing import Iterator

from ..domain.models import Airport, AirwayLeg, Fix, Leg, Procedure, Runway
from ..geo import haversine_km
from .primitives import decode_ident, decode_lat, decode_lon, decode_name6
from .tables import (
    ALT_DESC, FIX_TABLES, KIND_OF, NAVAID_NIBBLES, OPTIONAL_FILES, PATH_TERM,
    PROCEDURE_FILES, REQUIRED_FILES, SECTION_KIND, SECTION_TABLE,
)

# guarda contra saltos falsos dentro de uma corrida de aerovia (ver airways())
AIRWAY_MAX_LEG_KM = 300
# alvo de navaid alem disso do aerodromo e considerado bit VOR/DME trocado
NAVAID_ANCHOR_KM = 800


def _fix_km(a: Fix, b: Fix) -> float:
    return haversine_km(a.lat, a.lon, b.lat, b.lon)


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
        wanted = REQUIRED_FILES | OPTIONAL_FILES
        if self.source.is_dir():
            for name in wanted:
                for p in self.source.rglob(name):
                    self._raw[name] = p.read_bytes()
                    break
        else:
            with zipfile.ZipFile(self.source) as z:
                for info in z.infolist():
                    base = Path(info.filename).name
                    if base in wanted:
                        self._raw[base] = z.read(info)
        missing = REQUIRED_FILES - set(self._raw)
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
            return haversine_km(anchor[0], anchor[1], fix.lat, fix.lon)

        best = primary
        best_d = far(primary)
        if best_d <= NAVAID_ANCHOR_KM:
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
        de uma corrida de fixos em AWY_SEQ. Os registros estao em ordem
        crescente de inicio no arquivo, entao o fim de cada corrida e o inicio
        do PROXIMO registro (na ordem do arquivo, nao por nome). Um mesmo
        designador pode aparecer em varios registros consecutivos (sub-segmentos
        regionais de "M725", p.ex.) — cada um e uma corrida propria.

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
                if fix is not None and prev is not None and _fix_km(prev, fix) < AIRWAY_MAX_LEG_KM:
                    yield AirwayLeg("", prev, fix)
                prev = fix
            return

        recs = []
        for i in range(len(awy) // 8):
            name = decode_ident(int.from_bytes(awy[i * 8:i * 8 + 4], "big"))
            # indice inicial em AWY_SEQ: start = ptr/128 - 1 (calibrado vs CSV ER,
            # erro zero em todas as aerovias)
            start = (int.from_bytes(awy[i * 8 + 4:i * 8 + 8], "big") >> 7) - 1
            recs.append((name, start))

        # Dentro de uma corrida ainda aparecem saltos falsos (fixos nao sao
        # todos sequenciais). O limiar de 300 km evita DCT falso (ex.:
        # DIDAB->NIPDA 558 km) e cobre qualquer perna continental real.
        for k, (name, start) in enumerate(recs):
            end = recs[k + 1][1] if k + 1 < len(recs) else n_seq
            if not (0 <= start < end <= n_seq):
                continue
            prev = None
            for i in range(start, end):
                fix = self._airway_fix(struct.unpack_from(">I", buf, i * 8)[0])
                if fix is not None and prev is not None:
                    if _fix_km(prev, fix) < AIRWAY_MAX_LEG_KM:
                        yield AirwayLeg(name, prev, fix)
                prev = fix

    # --------------------------------------------------- procedimentos

    def _procedures(self, kind: str) -> Iterator[Procedure]:
        link_f, hdr_f, seq_f = PROCEDURE_FILES[kind]
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
                legs.append(Leg(
                    seq=j - first + 1,
                    path_term=PATH_TERM.get(sr[0], "??"),
                    fix=self._seq_fix(int.from_bytes(sr[4:8], "big"), sr[3], anchor),
                    altitude_ft=alt or None,
                    alt_desc=ALT_DESC[(sr[3] >> 4) & 3] if alt else "",
                    distance_nm=float(dist) if dist else None,
                    rnp=sr[12] * 5 / 100 if sr[12] else None,
                ))
            yield Procedure(kind, apt.icao, decode_name6(rec),
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
