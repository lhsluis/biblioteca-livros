# Deploy da Estante no Synology (Container Manager)

Sobe a Estante como um projeto do Container Manager, usando `docker-compose.synology.yml`:

- **estante**: Flask + Gunicorn (1 worker, 4 threads), porta 5000 do container publicada só em `127.0.0.1:8080` do NAS.
- A pasta de livros entra montada **somente leitura**. O cache (capas, índice e chave de sessão) fica em `data/cache`.

Não há banco, Redis, nginx nem backup. O cache é regenerável: se for perdido, o app reescaneia e gera as capas de novo (demora, mas não perde dados dos livros).

O login usa cookie `Secure`, então o acesso correto é por HTTPS (seção 5). Este guia assume o terminal SSH do NAS. Os comandos usam `docker compose`; se não existir no DSM, use `sudo -i` antes ou `docker-compose`.

> **Ainda não validado em produção.** Nenhuma das verificações abaixo foi rodada no NAS até este guia ser escrito. Rode o roteiro da seção 4 na primeira subida e anote o resultado.

---

## 1. Pré-requisitos

- DSM 7.2 ou superior, com o pacote **Container Manager** instalado.
- Acesso ao File Station ou SSH (usuário admin).
- Para acesso pelo domínio: um domínio apontando para o IP público da casa (DDNS, se o IP muda) e a porta 443 encaminhada no roteador para o NAS. Só pela LAN, o login não se mantém (cookie `Secure`).
- Pasta de livros já existente no NAS, por exemplo `/volume1/livros`.

## 2. Copiar o projeto e preparar as pastas

Crie `/volume1/docker/estante` e copie o projeto para ela **sem** `.cache`, `__pycache__`, `.pytest_cache`, `.git`, `tests`, `CLAUDE.md`, `.claude` e sem nenhum `.env` local. O `.dockerignore` já deixa esses itens de fora da imagem, mas não devem estar na pasta do NAS.

Crie a pasta do cache e dê a posse ao uid/gid definidos em `APP_UID`/`APP_GID` no `.env` (padrão 1000:1000):

```sh
mkdir -p /volume1/docker/estante/data/cache
chown -R 1000:1000 /volume1/docker/estante/data/cache
```

Sem isso, o app não consegue gravar as capas nem a chave de sessão (`.cache/secret.key`). Se mudar `APP_UID`/`APP_GID` no `Dockerfile`, use o mesmo número no `chown`.

A pasta de livros só precisa de leitura para o container (o mount é `:ro`). Não é preciso mudar a posse dela.

## 3. Configurar o `.env`

Na pasta do projeto:

```sh
cd /volume1/docker/estante
cp .env.synology.example .env
```

Preencha:

- `LIB_PSWD`: senha de acesso à biblioteca. Gere uma forte com `python -c "import secrets; print(secrets.token_urlsafe(24))"`. Sem espaços.
- `LIVROS_HOST_DIR`: caminho absoluto da pasta de livros no NAS (ex.: `/volume1/livros`).
- `HTTP_PORT=8080` (padrão). Não use 80 nem 443, que são do DSM.
- `SESSION_COOKIE_SECURE=true` (padrão). Use `false` só para testar por `http://IP:8080`, e volte para `true` depois.
- `CACHE_DIR` é opcional. Se usar outro caminho, faça o `chown` da seção 2 nele.

O `.env` nunca vai para o git (já está no `.gitignore`). O Container Manager lê o `.env` automaticamente.

## 4. Criar o projeto no Container Manager

1. **Container Manager → Projeto → Criar**.
2. Nome: `estante`. Caminho: `/volume1/docker/estante`.
3. Em "Fonte", escolha **Usar docker-compose.yml existente** e selecione `docker-compose.synology.yml`.
4. Se a versão do DSM aceitar apenas o nome padrão, copie `docker-compose.synology.yml` para `docker-compose.yml` na mesma pasta e use esse arquivo.
5. Avance e conclua. Clique em **Criar e iniciar** (ou **Build**). O primeiro build demora, porque instala as dependências.

### Roteiro de verificação (rodar no NAS, pelo SSH)

```sh
cd /volume1/docker/estante

# 1. Compose válido com o seu .env (não imprime segredos; só valida)
docker compose -f docker-compose.synology.yml config -q && echo "compose OK"

# 2. Build e subida
docker compose -f docker-compose.synology.yml up -d --build
docker compose -f docker-compose.synology.yml ps          # estante: healthy (pode levar até ~2 min)

# 3. Resposta HTTP local (a tela de login deve responder 200)
curl -sI http://127.0.0.1:8080/login | head -1

# 4. Cache das capas: pegue o id de uma capa no navegador (URL /covers/ID.jpg) e teste.
#    Esperado: cache-control com max-age=2592000 (30 dias). Sem sessão, pode vir redirect para o login; isso é normal.
curl -sI http://127.0.0.1:8080/covers/ID.jpg | grep -i cache-control
```

Se `ps` mostrar `starting` por mais tempo que o normal, veja o log (seção 8). Na primeira varredura de uma biblioteca grande, o health pode demorar a ficar `healthy`.

No navegador, abra `https://seu.dominio` (seção 5) e faça login com `LIB_PSWD`. A lista de livros deve aparecer, com as capas sendo geradas na primeira vez.

**Ainda não validado em produção:** rode o roteiro acima e registre o resultado antes de considerar o deploy pronto.

## 5. Reverse proxy HTTPS do DSM (acesso pelo domínio)

No **Painel de Controle → Portal de login → Avançado → Proxy reverso**:

1. Clique em **Criar**.
2. Origem: protocolo `HTTPS`, nome de host = seu domínio, porta `443`.
3. Destino: protocolo `HTTP`, nome de host `localhost`, porta `8080` (o valor de `HTTP_PORT`).
4. Não precisa de WebSocket.

Em **Painel de Controle → Segurança → Certificado**, crie ou importe um certificado **Let's Encrypt** para o domínio e associe-o ao proxy reverso. A renovação é automática, feita pelo DSM.

**Por que `TRUST_PROXY_HOPS=1` importa:** o login bloqueia o IP após 5 senhas erradas em 10 minutos. Com o DSM na frente, a conexão chega ao container vinda do próprio proxy. `TRUST_PROXY_HOPS=1` faz o app usar o IP real do cliente (vindo do cabeçalho `X-Forwarded-For`) para o bloqueio. Sem isso, todos os acessos pareceriam vir do mesmo IP e um erro de senha bloquearia todo mundo. O compose já define `1`; só mude se você acessar o container sem passar pelo proxy.

**Por que o login só se mantém via HTTPS:** com `SESSION_COOKIE_SECURE=true`, o navegador só guarda o cookie de sessão em conexão HTTPS. Por `http://IP:8080` a tela de login abre, mas a sessão não persiste. Use o domínio HTTPS para uso normal.

Depois de configurar, confira `https://seu.dominio/login` no navegador e o cadeado válido.

## 6. Atualização de versão

1. Copie os arquivos novos para `/volume1/docker/estante`. **Mantenha** o `.env` e a pasta `data/`.
2. Rode o script, que rebuilda e sobe o container:

   ```sh
   cd /volume1/docker/estante
   sh scripts/update.sh
   ```

   Ou manualmente: `docker compose -f docker-compose.synology.yml build --pull` e depois `docker compose -f docker-compose.synology.yml up -d`.
3. Confira com `docker compose -f docker-compose.synology.yml ps` (deve voltar a `healthy`) e pelo navegador.

Não há backup nem restauração neste projeto. Se precisar voltar a uma versão anterior, copie os arquivos antigos de volta e rode `sh scripts/update.sh` de novo. O cache é regenerável; se for apagado, o app reescaneia e gera as capas na próxima subida.

## 7. Logs e manutenção

- Pelo Container Manager: **Projeto `estante` → Log**.
- Pelo SSH: `docker compose -f docker-compose.synology.yml logs -f estante`.
- Os logs têm rotação (10 MB, 3 arquivos).
- O container reinicia sozinho (`restart: unless-stopped`).
- Para atualizar a biblioteca sem reiniciar, use o botão **"Atualizar biblioteca"** no topo da página, ou reinicie o container.
- Limite de memória (`mem_limit`) está comentado no compose. Descomente se o NAS ficar sem RAM.
- Para limpar o cache, pare o container, apague `data/cache` e suba de novo: o app regenera as capas. Isso também troca a chave de sessão, então todos precisam logar de novo.

## 8. Problemas comuns

- **Permissão no cache (`Permission denied` no log):** o `chown` da seção 2 não foi feito, ou o uid não bate com `APP_UID`/`APP_GID` do `.env` (depois de mudar, rode o build de novo). Rode `chown -R 1000:1000 /volume1/docker/estante/data/cache` e reinicie.
- **Login não persiste pelo IP:** é o esperado com `SESSION_COOKIE_SECURE=true`. Use o domínio HTTPS (seção 5).
- **Container fica `unhealthy` ou reinicia na primeira subida:** a primeira varredura de uma biblioteca grande pode passar do timeout de 120 s do gunicorn (`--timeout 120`, no `CMD` do `Dockerfile`). Procure `WORKER TIMEOUT` no log. Se acontecer, reinicie o container e veja se a varredura termina na tentativa seguinte. O `start_period` do healthcheck é 120 s. Ainda não validado com uma biblioteca grande.
- **`LIB_PSWD` ou `LIVROS_HOST_DIR` ausente:** o `docker compose config` falha com "defina no .env". Confira o `.env`.
- **Pasta de livros vazia:** confira se `LIVROS_HOST_DIR` aponta para a pasta certa e se o DSM dá leitura ao usuário que roda o Docker.
