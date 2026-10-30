import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

import app as app_module


def _login_falho(client, ip):
    return client.post(
        "/login",
        data={"password": "errada"},
        headers={"X-Forwarded-For": ip},
    )


def _bloqueado(resp):
    return "Muitas tentativas".encode() in resp.data


@pytest.fixture
def proxy_ativo():
    """Liga o ProxyFix (1 proxy na frente) só durante o teste e restaura depois."""
    original = app_module.app.__dict__.get("wsgi_app")
    app_module.app.wsgi_app = ProxyFix(
        app_module.app.wsgi_app, x_for=1, x_proto=1, x_host=1,
    )
    yield
    if original is None:
        del app_module.app.wsgi_app
    else:
        app_module.app.wsgi_app = original


def test_proxyfix_separa_falhas_por_ip_do_x_forwarded_for(client, proxy_ativo):
    for _ in range(app_module.LOGIN_MAX_FALHAS):
        _login_falho(client, "203.0.113.1")
    assert _bloqueado(_login_falho(client, "203.0.113.1"))
    # Outro cliente atrás do mesmo proxy não pode ser bloqueado pelo primeiro.
    assert not _bloqueado(_login_falho(client, "203.0.113.2"))


def test_sem_proxyfix_usa_remote_addr_e_ignora_x_forwarded_for(client):
    for _ in range(app_module.LOGIN_MAX_FALHAS):
        _login_falho(client, "203.0.113.1")
    # Sem ProxyFix todas as tentativas vêm do remote_addr do teste (127.0.0.1).
    assert _bloqueado(_login_falho(client, "203.0.113.2"))


def test_cookie_de_sessao_httponly_e_samesite_lax():
    assert app_module.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_module.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
