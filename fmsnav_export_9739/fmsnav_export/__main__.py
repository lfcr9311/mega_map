"""CLI: python -m fmsnav_export CICLO.zip --cycle 2607 --out ./out [--area SB]"""
import argparse

from .build import build


def main():
    ap = argparse.ArgumentParser(
        prog="fmsnav_export",
        description="Le o banco binario .S01 (zip do ciclo) e gera JSONs por "
                    "parametro + planejador HTML standalone.",
    )
    ap.add_argument("zip", help="zip do ciclo contendo os arquivos .S01")
    ap.add_argument("--out", default="./out", help="diretorio de saida (default ./out)")
    ap.add_argument("--cycle", default="2607", help="rotulo do ciclo AIRAC")
    ap.add_argument("--area", default=None,
                    help="filtro por prefixo ICAO, ex.: SB (Brasil). "
                         "Separe varios por virgula. Omitir = mundo inteiro.")
    ap.add_argument("--html-name", default="planejador.html",
                    help="nome do arquivo HTML de saida")
    a = ap.parse_args()

    build(
        a.zip,
        out=a.out,
        cycle=a.cycle,
        area=a.area.split(",") if a.area else None,
        html_name=a.html_name,
    )


if __name__ == "__main__":
    main()
