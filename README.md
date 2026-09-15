# Estante — O visualizador mais simples para livros 

Aplicação web local (Flask) que varre recursivamente uma pasta de livros —
não importa a estrutura de subpastas — e mostra cada arquivo como um
cartão com capa, agrupado em fileiras por autor. Clique na capa para abrir
o livro.

## Formatos suportados
`.pdf` `.epub` `.txt` `.doc` `.docx` `.mobi` `.azw` `.azw3` `.rtf` `.odt` `.fb2`

## Como funciona a "autoria"
O autor de cada livro é o nome da subpasta imediatamente dentro da pasta
raiz (ex.: `Livros/Machado de Assis/dom-casmurro.epub` → autor
"Machado de Assis"). Arquivos soltos direto na raiz caem em "Desconhecido".

## Como funcionam as capas
- **EPUB**: extrai a imagem de capa real declarada dentro do arquivo.
- **PDF**: renderiza a primeira página como imagem (biblioteca PyMuPDF).
- **DOCX**: usa a primeira imagem embutida no documento, se existir.
- **Demais formatos** (doc, txt, mobi, azw3, rtf, odt, fb2) ou quando a
  extração falha: gera uma capa ilustrada com o título, autor e formato.

As capas geradas ficam em cache na pasta `.cache/`, então a partir da
segunda execução o carregamento é praticamente instantâneo — só livros
novos ou alterados são reprocessados.

## Tela de login

O acesso à biblioteca é protegido por senha, definida de uma das duas
formas (a variável de ambiente tem prioridade sobre o argumento):

```bash
# variável de ambiente (recomendado, principalmente em container/servidor)
LIB_PSWD="minha-senha" python app.py

# ou como segundo argumento posicional na linha de comando
python app.py /caminho/para/Livros minha-senha
```

Se nenhuma das duas for informada, a aplicação sobe mesmo assim usando a
senha padrão `change-it` — só que avisa isso no terminal. Não deixe o
padrão em produção.

> Evite passar a senha como argumento em servidores compartilhados: ela
> fica visível no histórico do shell e para qualquer usuário que rodar
> `ps aux` enquanto o processo estiver no ar. Prefira sempre `LIB_PSWD`.

Depois de logar uma vez, a sessão fica salva por 30 dias (mesmo navegador),
então não é preciso digitar a senha a cada visita. Há um link "Sair" no
topo da página para encerrar a sessão manualmente.

## Deploy com em "Produção" com Docker

O projeto já vem com `Dockerfile`, `.dockerignore` e `docker-compose.yml`
prontos. Em produção, a aplicação roda atrás do **gunicorn** (não do
servidor de desenvolvimento do Flask).

### Passo a passo com docker-compose (recomendado e mais fácil)

1. Abra o `docker-compose.yml` e ajuste:
   - `LIB_PSWD`: a senha de acesso.
   - O caminho à esquerda de `:/data/livros:ro`: o caminho real da sua
     pasta de livros no host.
2. Suba:
   ```bash
   docker compose up -d --build
   ```
3. Acesse `http://localhost:5000`. 

### Só com Docker (sem compose)

```bash
docker build -t estante-livros .

docker run -d \
  --name estante-livros \
  -p 5000:5000 \
  -e LIB_PSWD="troque-esta-senha" \
  -v /caminho/absoluto/para/Livros:/data/livros:ro \
  -v estante-cache:/app/.cache \
  --restart unless-stopped \
  estante-livros
```

### Por que só 1 worker?

O `Dockerfile` sobe o gunicorn com `--workers 1 --threads 4`. O cache de
capas (`.cache/index.json`) e a chave de sessão (`.cache/secret.key`) são
lidos e escritos em arquivo, sem lock — com mais de um *worker* (processo),
cada um escaneia a biblioteca de forma independente e pode haver corrida
na escrita desses arquivos. `--threads` dá concorrência dentro do mesmo
processo sem esse problema, o que é mais que suficiente para uma
biblioteca pessoal.

### Sobre os volumes

- `/data/livros` — sua pasta de livros, montada **somente leitura** (a
  aplicação nunca escreve nela).
- `/app/.cache` — capas geradas, índice de cache e chave de sessão.
  Use um volume nomeado (como no `docker-compose.yml`) para que isso
  sobreviva a reinícios e rebuilds do container; caso contrário, toda
  atualização de imagem reprocessa todas as capas do zero e derruba as
  sessões de login ativas.

### Atualizar a biblioteca depois do deploy

Adicionou ou removeu livros com o container já rodando? Clique em
**"Atualizar biblioteca"** no topo da página — ele reescaneia tudo
(usando a sessão do navegador, que já está autenticada) e recarrega a
lista sem precisar reiniciar nada.

Reiniciar o container (`docker compose restart`) também funciona, e
reescaneia tudo no início.

## Instalação local

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python app.py /caminho/completo/para/Livros
```

ou definindo a variável de ambiente:

```bash
export LIVROS_DIR="/caminho/completo/para/Livros"
python app.py
```

Depois abra **http://127.0.0.1:5000** no navegador.

Ao clicar num livro:
- **EPUB** abre um leitor dentro do próprio navegador (usando a
  biblioteca [epub.js](https://github.com/futurepress/epub.js)), com
  navegação por página, arraste em telas de toque e indicador de
  progresso.
- **PDF e TXT** abrem direto numa nova aba do navegador.
- **DOC, DOCX** e os demais formatos são baixados, porque o navegador
  não sabe exibi-los nativamente.

> O leitor de EPUB carrega a biblioteca epub.js a partir de um CDN
> (jsdelivr), então é necessário ter conexão com a internet para essa
> tela específica — o restante da aplicação (escaneamento, capas,
> download dos arquivos) funciona 100% offline. Se o EPUB não puder ser
> aberto no leitor por algum motivo, a página mostra um aviso com um
> link para baixar o arquivo original.

## Buscar

O campo de busca no topo filtra por título ou autor em tempo real, sem
recarregar a página.

## Atualizar a biblioteca sem reiniciar

Se adicionar ou remover livros com o servidor já rodando, clique em
**"Atualizar biblioteca"** no topo da página — ele chama a rota
`/rescan` usando a sessão do navegador (que já está logada) e recarrega
a lista automaticamente. Reiniciar o servidor também funciona.

## Notas
- Para pastas muito grandes, a primeira execução pode demorar alguns
  minutos, já que cada capa (principalmente as renderizadas de PDF)
  precisa ser gerada uma vez.
- Arquivos `.doc` antigos e a maioria dos `.docx`/`.txt`/`.rtf` recebem
  uma capa ilustrada, pois esses formatos normalmente não trazem uma
  imagem de capa embutida.