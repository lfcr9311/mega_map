"""Primitivas de decodificacao — validadas 100% contra os CSVs oficiais.

  texto      simbolos de 6 bits, deslocamentos 26/20/14/8/2 num uint32 BE;
             digitos nos codigos 14-23, letras em 30-55, hifen em 11.
             Nomes de 6 caracteres levam o sexto nos bits 32-37.
  latitude   uint24 BE / 80000 graus, complemento acima de 90
  longitude  uint24 BE / 40000 graus, complemento acima de 180
"""
from __future__ import annotations

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


def decode_lat(rec: bytes, off: int) -> float:
    v = int.from_bytes(rec[off:off + 3], "big") / 80000.0
    return v - 2 ** 24 / 80000.0 if v > 90 else v


def decode_lon(rec: bytes, off: int) -> float:
    v = int.from_bytes(rec[off:off + 3], "big") / 40000.0
    return v - 2 ** 24 / 40000.0 if v > 180 else v
