"""
app.py
------
Servidor local que exibe sua pasta de livros como uma "vitrine" estilo
Netflix: um cartão com capa para cada livro, agrupados em fileiras por
autor, independente de qual seja o formato do arquivo.

Uso:
    python app.py /caminho/para/Livros senha
    (ou defina as variáveis de ambiente LIVROS_DIR e LIB_PSWD)

    LIVROS_DIR: pasta com os livros (1º argumento como alternativa).
    LIB_PSWD:   senha de acesso à biblioteca (2º argumento como alternativa).
    Se nenhuma for definida, usa a senha padrão 'change-it' e avisa no terminal.

Depois abra http://127.0.0.1:5000 no navegador.
"""

import os
import sys
import json
import hmac
import mimetypes
import threading
import time
import unicodedata
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask, render_template, send_file, abort, jsonify,
    session, request, redirect, url_for,
)

from werkzeug.middleware.proxy_fix import ProxyFix

from scanner import scan_library
import cover_extractor as covers

BASE_DIR = Path(__file__).parent.resolve()
CACHE_DIR = BASE_DIR / ".cache"
COVERS_DIR = CACHE_DIR / "covers"
INDEX_FILE = CACHE_DIR / "index.json"
SECRET_KEY_FILE = CACHE_DIR / "secret.key"

COVERS_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_secret_key() -> bytes:
    """Gera uma chave de sessão na primeira execução e reaproveita depois,
    para que o login não precise ser refeito a cada reinício do servidor."""
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_bytes()
    key = os.urandom(32)
    SECRET_KEY_FILE.write_bytes(key)
    return key


app = Flask(__name__)
app.secret_key = get_or_create_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Uso: python app.py [diretorio_dos_livros] [senha]
# Cada valor pode vir por variável de ambiente (prioridade) ou por
# argumento posicional na linha de comando.
LIBRARY_DIR = os.environ.get("LIVROS_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "Livros")
LIBRARY_PASSWORD = os.environ.get("LIB_PSWD") or (sys.argv[2] if len(sys.argv) > 2 else "change-it")
# Atrás do reverse proxy HTTPS do DSM: quantos proxies confiar nos X-Forwarded-*.
# 0 = nenhum (dev local); 1 = um proxy na frente (caso do Synology).
TRUST_PROXY_HOPS = int(os.environ.get("TRUST_PROXY_HOPS", "0"))
# Cookie de sessão só trafega por HTTPS quando ativado (ligue em produção).
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")

app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if TRUST_PROXY_HOPS > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=TRUST_PROXY_HOPS, x_proto=TRUST_PROXY_HOPS, x_host=TRUST_PROXY_HOPS,
    )
 
if LIBRARY_PASSWORD == "change-it":
    print("[AVISO] Nenhuma senha definida (LIB_PSWD ou 2º argumento). "
          "Usando a senha padrão 'change-it' — troque antes de expor a app na rede.")

_books_by_id = {}


@app.before_request
def require_login():
    """Bloqueia todas as rotas, exceto a de login e os arquivos estáticos,
    até que a senha correta tenha sido informada."""
    if request.endpoint in ("login", "static"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))


LOGIN_MAX_FALHAS = 5
LOGIN_JANELA_SEGUNDOS = 600  # 10 minutos

_falhas_login = {}  # IP -> lista de instantes das falhas recentes
_falhas_lock = threading.Lock()


def _safe_next(url):
    """Aceita só caminhos internos. '//' e '/\\' viram URL externa no navegador,
    então caem no índice."""
    if (url and url.startswith("/") and not url.startswith(("//", "/\\"))
            and not any(c in url for c in "\t\r\n")):
        return url
    return url_for("index")


def _login_bloqueado(ip):
    """Diz se o IP excedeu as falhas permitidas na janela de tempo."""
    agora = time.time()
    with _falhas_lock:
        recentes = [t for t in _falhas_login.get(ip, []) if agora - t < LOGIN_JANELA_SEGUNDOS]
        if recentes:
            _falhas_login[ip] = recentes
        else:
            _falhas_login.pop(ip, None)
        return len(recentes) >= LOGIN_MAX_FALHAS


def _registrar_falha(ip):
    with _falhas_lock:
        _falhas_login.setdefault(ip, []).append(time.time())


def _limpar_falhas(ip):
    with _falhas_lock:
        _falhas_login.pop(ip, None)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    next_url = _safe_next(request.values.get("next"))
    ip = request.remote_addr

    if request.method == "POST":
        if _login_bloqueado(ip):
            error = "Muitas tentativas. Aguarde alguns minutos."
        else:
            entered = request.form.get("password", "")
            if hmac.compare_digest(entered.encode(), LIBRARY_PASSWORD.encode()):
                _limpar_falhas(ip)
                session.permanent = True
                session["authenticated"] = True
                return redirect(_safe_next(request.form.get("next")))
            _registrar_falha(ip)
            error = "Senha incorreta."

    return render_template("login.html", error=error, next=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


def load_cover_index():
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cover_index(index):
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_cover(book, index: dict):
    """Gera a capa apenas se ainda não existir em cache ou se o arquivo mudou."""
    cover_path = COVERS_DIR / f"{book.id}.jpg"
    entry = index.get(book.id)
    if entry and entry.get("mtime") == book.mtime and cover_path.exists():
        return
    data = covers.get_cover_bytes(book)
    cover_path.write_bytes(data)
    index[book.id] = {"mtime": book.mtime, "title": book.title, "author": book.author}


# Evita dois rescans simultâneos escreverem o index.json ao mesmo tempo.
_build_lock = threading.Lock()


def build_library():
    global _books_by_id
    with _build_lock:
        books = scan_library(LIBRARY_DIR)
        index = load_cover_index()

        for b in books:
            ensure_cover(b, index)
            b.cover_url = f"/covers/{b.id}.jpg?v={int(b.mtime)}"

        # Remove capas de livros que sumiram da pasta (entrada e .jpg).
        ids_atuais = {b.id for b in books}
        if not books:  # pasta indisponível/vazia: não apaga o cache inteiro
            ids_atuais = set(index)
        for book_id in list(index):
            if book_id not in ids_atuais:
                index.pop(book_id, None)
                (COVERS_DIR / f"{book_id}.jpg").unlink(missing_ok=True)

        # Remove .jpg órfãos que não correspondem a nenhum livro.
        for jpg in COVERS_DIR.glob("*.jpg"):
            if jpg.stem not in ids_atuais:
                jpg.unlink(missing_ok=True)

        save_cover_index(index)
        _books_by_id = {b.id: b for b in books}
        return books


def _chave_sem_acento(texto):
    """'Álvares' -> 'alvares': remove marcas de acento para ordenar e indexar."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").lower()


@app.route("/")
def index():
    books = list(_books_by_id.values())
    authors = {}
    for b in books:
        authors.setdefault(b.author, []).append(b)
    authors = dict(sorted(
        authors.items(),
        key=lambda kv: (_chave_sem_acento(kv[0]), kv[0].lower()),
    ))
    letter_targets = {}
    for position, author in enumerate(authors):
        letter = _chave_sem_acento(author)[:1].upper()
        letter_targets.setdefault(letter, f"author-{position}")

    # Fileira "Adicionados recentemente": só aparece com mais de 12 livros.
    recent = sorted(books, key=lambda b: b.mtime, reverse=True)[:12] if len(books) > 12 else []

    return render_template(
        "index.html",
        authors=authors,
        letter_targets=letter_targets,
        recent=recent,
        total=len(books),
        library_dir=str(Path(LIBRARY_DIR).expanduser().resolve()),
    )


@app.route("/covers/<book_id>.jpg")
def cover(book_id):
    path = COVERS_DIR / f"{book_id}.jpg"
    if not path.exists():
        abort(404)
    # Capa muda quando o livro muda; a URL versionada (?v=mtime) cuida disso.
    return send_file(path, mimetype="image/jpeg", max_age=60 * 60 * 24 * 30)


@app.route("/book/<book_id>")
def open_book(book_id):
    book = _books_by_id.get(book_id)
    if not book:
        abort(404)

    path = Path(book.path)
    if not path.exists():
        abort(404)

    mimetype, _ = mimetypes.guess_type(str(path))
    # PDF e TXT abrem direto no navegador; os demais formatos são baixados,
    # já que o navegador não sabe exibi-los nativamente.
    inline_formats = {"pdf", "txt"}
    as_attachment = book.ext not in inline_formats

    return send_file(
        path,
        mimetype=mimetype,
        as_attachment=as_attachment,
        download_name=path.name,
    )


@app.route("/read/<book_id>")
def read_book(book_id):
    """Página de leitura de EPUB dentro do próprio navegador, usando epub.js."""
    book = _books_by_id.get(book_id)
    if not book or book.ext != "epub":
        abort(404)
    return render_template("reader.html", book=book)


@app.route("/book/<book_id>/raw.epub")
def book_raw(book_id):
    """Serve o EPUB como binário inline, para o epub.js buscar via fetch/XHR.
    A URL termina em .epub de propósito: é o sinal que o epub.js usa para
    saber que deve baixar o arquivo inteiro e abri-lo como um .epub
    compactado, em vez de tratá-lo como uma pasta já descompactada."""
    book = _books_by_id.get(book_id)
    if not book or book.ext != "epub":
        abort(404)

    path = Path(book.path)
    if not path.exists():
        abort(404)

    return send_file(path, mimetype="application/epub+zip", as_attachment=False)


@app.route("/rescan", methods=["POST"])
def rescan():
    build_library()
    return jsonify({"status": "ok", "total": len(_books_by_id)})


# Escaneia a biblioteca assim que o módulo é carregado — funciona tanto
# rodando "python app.py" (dev) quanto atrás de um servidor WSGI como o
# gunicorn (container/produção), que só importa "app.py" e nunca executa
# o bloco "if __name__ == '__main__'" abaixo.
print(f"Escaneando biblioteca em: {Path(LIBRARY_DIR).expanduser().resolve()}")
build_library()
print(f"{len(_books_by_id)} livro(s) encontrado(s). Capas em cache atualizadas.")                                                                    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
