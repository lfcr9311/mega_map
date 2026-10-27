"""Layout das tabelas .S01 e codigos de mapeamento."""
from __future__ import annotations

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
# consistencia geografica com o aerodromo (ver FmsDatabase._seq_fix).
NAVAID_NIBBLES = frozenset({0x7, 0x8, 0x9, 0xA, 0xB, 0xC})

# descritor de altitude: bits 4-5 do byte 3 da perna (validado 100% vs CSV)
ALT_DESC = {0: "+", 1: "-", 2: "", 3: "B"}

# arquivos lidos do zip; os opcionais tem fallback no reader
REQUIRED_FILES = frozenset({
    "WPT_ENRT.S01", "WPT_TERM.S01", "AIRPORT.S01", "RUNWAY.S01",
    "VOR.S01", "VOR_DMEC.S01", "VOR_DMEN.S01", "NDB_ENRT.S01",
    "NDB_TERM.S01", "DME.S01", "ILS_DMEN.S01",
    "AWY_SEQ.S01",
    "SID.S01", "STAR.S01", "APPR.S01",
    "SID_SEQ.S01", "STAR_SEQ.S01", "APPR_SEQ.S01",
    "ARPT_SID.S01", "ARPT_STA.S01", "ARPT_APP.S01",
})
OPTIONAL_FILES = frozenset({"LK_FX_AW.S01", "AIRWAY.S01", "STANDARD.HD"})

PROCEDURE_FILES = {
    "SID": ("ARPT_SID.S01", "SID.S01", "SID_SEQ.S01"),
    "STAR": ("ARPT_STA.S01", "STAR.S01", "STAR_SEQ.S01"),
    "APPR": ("ARPT_APP.S01", "APPR.S01", "APPR_SEQ.S01"),
}
