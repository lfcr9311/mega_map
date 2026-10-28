"""Sentido das aerovias a partir da eAIP Brasil (DECEA, ENR 3.2).

O banco do FMS nao traz o sentido das aerovias: comparado com a AIP perna a
perna, pernas com todos os bits iguais sao de mao dupla, de sentido unico no
sentido gravado ou no contrario (docs/DOCUMENTACAO_COMPLETA.md §4.5). O
sentido vem entao da coluna "Direcao do nivel de cruzeiro" da ENR 3.2, que
para cada trecho traz uma seta por paridade de nivel (Impar | Par):

    ↓  o trecho e voado no sentido da tabela (de cima para baixo)
    ↑  no sentido contrario
    x  nao ha niveis dessa paridade
    uma celula so (colspan=2) vale para as duas paridades

Sentido unico = so uma das direcoes aparece. Cobre so o espaco aereo brasileiro.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

EAIP_URL = "https://aisweb.decea.mil.br/eaip"

# 2001 entrou em vigor em 02/01/2020; os ciclos AIRAC tem 28 dias
_AIRAC_REF = date(2020, 1, 2)

_POINT_ROW = r'<tr id="(?P<pt>[A-Z0-9]{2,5})" style="text-align: left" valign="middle"'
_ARROW_CELL = (r'<td(?P<td>[^>]*)>\s*<span[^>]*>\s*<span[^>]*font-size:40px;">\s*'
               r'(?P<sym>[^<\s]*)\s*<')
_TOKENS = re.compile(f"{_POINT_ROW}|{_ARROW_CELL}")
_ROUTE_PAGE = re.compile(r"ENR 3\.2 ([A-Z0-9]+)-pt-BR\.html")
_AMDTS = re.compile(r"var amdts\s*=\s*(\[.*?\])\s*(?:;|\n)", re.S)


@dataclass(frozen=True, slots=True)
class Segment:
    """Trecho da ENR 3.2: `forward` = de `start` para `end` (ordem da tabela)."""
    route: str
    start: str
    end: str
    forward: bool
    backward: bool

    @property
    def one_way(self) -> bool:
        return self.forward != self.backward


def airac_date(cycle: str) -> date:
    """Data de vigencia do ciclo AIRAC "AANN" (ex.: 2610 -> 01/10/2026)."""
    year, num = 2000 + int(cycle[:2]), int(cycle[2:])
    d = _AIRAC_REF
    while d.year < year:
        d += timedelta(days=28)
    while d.year > year:
        d -= timedelta(days=28)
    while (d - timedelta(days=28)).year == year:
        d -= timedelta(days=28)
    d += timedelta(days=28 * (num - 1))
    if d.year != year:
        raise ValueError(f"ciclo AIRAC invalido: {cycle}")
    return d


def pick_amendment(index_html: str, effective: date) -> str:
    """Diretorio da emenda em vigor na data: a de vigencia mais recente <= data
    e, entre as de mesma vigencia, a publicada por ultimo."""
    m = _AMDTS.search(index_html)
    if not m:
        raise ValueError("lista de emendas nao encontrada na pagina da eAIP")
    best = None
    for a in json.loads(m.group(1)):
        eff = date(int(a["effective"]["year"]), int(a["effective"]["month"]), int(a["effective"]["day"]))
        pub = date(int(a["publication"]["year"]), int(a["publication"]["month"]), int(a["publication"]["day"]))
        if eff <= effective and (best is None or (eff, pub) > best[0]):
            best = ((eff, pub), a["dir"])
    if best is None:
        raise ValueError(f"nenhuma emenda da eAIP em vigor em {effective}")
    return best[1]


def route_pages(menu_html: str) -> list[str]:
    """Designadores das rotas da ENR 3.2 listadas no menu da emenda."""
    return sorted(set(_ROUTE_PAGE.findall(menu_html)))


def parse_route_page(html: str, route: str) -> tuple[list[Segment], list[str]]:
    """Trechos da rota, na ordem da tabela, e os problemas de leitura."""
    problems = []
    if 'class="deleted"' in html:
        problems.append(f"{route}: pagina tem trechos marcados como removidos; conferir a leitura")
    segments: list[Segment] = []
    last: str | None = None
    cols: list[str] = []
    for m in _TOKENS.finditer(html):
        if m.group("pt"):
            if last is not None:
                if len(cols) == 2:
                    segments.append(Segment(route, last, m.group("pt"), "↓" in cols, "↑" in cols))
                elif cols:
                    problems.append(f"{route}: {last}-{m.group('pt')} com {len(cols)} colunas de sentido")
            last, cols = m.group("pt"), []
        else:
            sym = m.group("sym")
            if sym not in ("↓", "↑", "x"):
                problems.append(f"{route}: simbolo de sentido desconhecido {sym!r} depois de {last}")
            cols += [sym] * (2 if 'colspan="2"' in m.group("td") else 1)
    return segments, problems


def fetch_segments(cycle: str, cache_dir: Path, log=print, client=None
                   ) -> tuple[str, list[Segment], list[str]]:
    """Baixa (ou le do cache) a ENR 3.2 da emenda em vigor no ciclo.

    Retorna (diretorio da emenda, trechos, problemas). O cache fica em
    `cache_dir/<emenda>/`, entao refazer o build nao baixa de novo.
    """
    import httpx

    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        def get(url: str, path: Path) -> str:
            if path.is_file():
                return path.read_text(encoding="utf-8")
            r = client.get(url)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.text, encoding="utf-8")
            time.sleep(0.2)              # um pedido por vez, sem pressa: servidor publico
            return r.text

        effective = airac_date(cycle)
        # o indice muda a cada emenda: tenta o atual, cai no do cache se estiver sem rede
        index_path = cache_dir / "index.html"
        try:
            r = client.get(EAIP_URL)
            r.raise_for_status()
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(r.text, encoding="utf-8")
            index = r.text
        except httpx.HTTPError:
            if not index_path.is_file():
                raise
            log(f"      eAIP fora do ar; usando o indice em cache ({index_path})")
            index = index_path.read_text(encoding="utf-8")
        amdt = pick_amendment(index, effective)
        base = f"{EAIP_URL}/{quote(amdt)}/eAIP"
        folder = cache_dir / amdt
        log(f"      eAIP {amdt} (ciclo {cycle} em vigor em {effective:%d/%m/%Y})")

        routes = route_pages(get(f"{base}/menu.html", folder / "menu.html"))
        segments: list[Segment] = []
        problems: list[str] = []
        for route in routes:
            html = get(f"{base}/{quote(f'ENR 3.2 {route}-pt-BR.html')}", folder / f"ENR 3.2 {route}.html")
            segs, probs = parse_route_page(html, route)
            if not segs:
                probs.append(f"{route}: nenhum trecho lido")
            segments += segs
            problems += probs
        return amdt, segments, problems
    finally:
        if own:
            client.close()
