# Deploy no EC2 (`/map`)

O app responde inteiro sob `/map`: frontend em `/map/`, API em `/map/api`, docs em
`/map/docs`. No EC2, o container publica `127.0.0.1:8001`. Quem atende a porta 80 só
precisa repassar `/map/*` para `127.0.0.1:8001`, sem mexer no caminho. A raiz `/` continua
com o outro app (Performance de Decolagem, `~/fortran`).

A cada push na `master`, `.github/workflows/deploy.yml` roda os testes, entra no EC2 por
SSH e roda `deploy/atualizar.sh`: `git pull`, `docker compose up -d --build`, conferência.

## Uma vez no EC2

```bash
git clone https://github.com/lfcr9311/mega_map.git ~/mega_map
```

## Uma vez no seu computador

O grafo não está no Git. Suba-o agora e a cada novo ciclo AIRAC:

```bash
make data
make deploy-data EC2_KEY=~/CHAVE.pem
```

Chave só para o deploy, limitada a rodar o `atualizar.sh` deste repositório:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gh_deploy_fmsnav -N "" -C github-actions-deploy-fmsnav
echo "command=\"bash ~/mega_map/deploy/atualizar.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat ~/.ssh/gh_deploy_fmsnav.pub)" \
  | ssh -i ~/CHAVE.pem -o IdentitiesOnly=yes ubuntu@ec2-3-137-219-87.us-east-2.compute.amazonaws.com 'cat >> ~/.ssh/authorized_keys'
```

`-o IdentitiesOnly=yes` garante que o ssh use só a chave indicada. Sem isso, ele pode usar
a chave de deploy do fortran, e essa dispara o deploy dele.

## Uma vez no GitHub: secrets

```bash
R=lfcr9311/mega_map
H=ec2-3-137-219-87.us-east-2.compute.amazonaws.com
gh secret set EC2_HOST -R $R -b "$H"
gh secret set EC2_USER -R $R -b "ubuntu"
gh secret set EC2_SSH_KEY -R $R < ~/.ssh/gh_deploy_fmsnav
ssh-keyscan -t ed25519 $H | gh secret set EC2_KNOWN_HOSTS -R $R
```

## Dia a dia

No EC2, em `~/mega_map`:
- `docker compose logs -f fmsnav`: log do servidor
- `bash deploy/atualizar.sh`: o mesmo deploy, rodado à mão
- `.env` (opcional): `FMSNAV_RPL_BACK_URL=...` liga o desvio de NOTAMs
