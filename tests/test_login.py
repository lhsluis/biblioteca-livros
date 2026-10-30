from urllib.parse import urlparse

import app as app_module

SENHA = "teste"


def _autenticado(client):
    with client.session_transaction() as sess:
        return bool(sess.get("authenticated"))


def _login(client, senha, next_url="/"):
    return client.post("/login", data={"password": senha, "next": next_url})


def test_senha_certa_autentica(client):
    resp = _login(client, SENHA)
    assert resp.status_code == 302
    assert _autenticado(client)


def test_senha_errada_nao_autentica(client):
    resp = _login(client, "errada")
    assert resp.status_code == 200
    assert b"Senha incorreta" in resp.data
    assert not _autenticado(client)


def test_next_externo_vira_index(client):
    resp = _login(client, SENHA, next_url="https://evil.example.com/")
    destino = urlparse(resp.headers["Location"])
    assert destino.netloc in ("", "localhost")
    assert destino.path == "/"


def test_logout_por_get_retorna_405(client):
    _login(client, SENHA)
    assert client.get("/logout").status_code == 405


def test_bloqueio_apos_5_falhas(client):
    for _ in range(app_module.LOGIN_MAX_FALHAS):
        _login(client, "errada")
    # Mesmo com a senha certa, o IP fica bloqueado nessa janela.
    resp = _login(client, SENHA)
    assert "Muitas tentativas".encode() in resp.data
    assert not _autenticado(client)
