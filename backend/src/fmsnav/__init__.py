"""fmsnav — banco de navegacao FMS (Thales .S01) e planejamento de rotas.

Camadas, da mais baixa para a mais alta:

    decode/    binario .S01 -> objetos de dominio (o nucleo validado)
    export/    objetos -> JSON por parametro + grafo compilado (navgraph)
    navgraph/  grafo compilado carregado em memoria (consultas, indice espacial)
    routing/   A*, procedimentos SID/STAR, desvio de areas, planejador
    notams/    integracao com o rpl_back (NOTAMs e areas especiais)
    api/       FastAPI expondo tudo isso ao frontend
"""
__version__ = "0.2.0"
