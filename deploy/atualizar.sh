#!/usr/bin/env bash
# =============================================================================
# Atualiza o servidor com o que esta no GitHub e reinicia o container.
#
# Chamado pelo GitHub Actions (.github/workflows/deploy.yml) a cada push na
# master. Tambem pode rodar a mao, no servidor:
#     bash ~/mega_map/deploy/atualizar.sh
#
# O grafo (data/build/navgraph.json.gz) nao esta no Git e nao e mexido; sobe
# com `make deploy-data` (ver deploy/README.md).
# =============================================================================
# Tudo dentro de { }: o bash le o script inteiro antes de rodar, porque o
# git reset abaixo pode trocar este proprio arquivo no meio da execucao.
{
set -euo pipefail

passo() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
falha() { printf '\n\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-master}"
cd "$DIR"
[ -f data/build/navgraph.json.gz ] || falha "Falta o $DIR/data/build/navgraph.json.gz. Rode no seu computador: make deploy-data"

passo "Baixando a $BRANCH do GitHub"
git fetch --quiet origin "$BRANCH"
git reset --quiet --hard "origin/$BRANCH"
git log -1 --format='    commit %h: %s (%an, %ar)'

passo "Reconstruindo e reiniciando o container"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null

passo "Conferindo se o programa responde"
for _ in $(seq 1 60); do
    code=$(docker compose exec -T fmsnav python3 -c '
import urllib.request
try:
    print(urllib.request.urlopen("http://127.0.0.1:8001/map/api/health", timeout=5).status)
except Exception:
    print(0)' 2>/dev/null || echo 0)
    [ "$code" = 200 ] && break
    sleep 2
done
if [ "$code" = 200 ]; then
    printf '    \033[32mOK\033[0m o programa respondeu (HTTP %s)\n' "$code"
else
    docker compose logs --tail 40 fmsnav; falha "O programa nao respondeu depois do deploy"
fi
exit 0
}
