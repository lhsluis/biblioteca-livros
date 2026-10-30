import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Biblioteca de teste vazia e senha fixa. Precisam existir ANTES do import de
# app.py, porque ele lê LIVROS_DIR/LIB_PSWD e escaneia a pasta ao ser carregado.
_LIVROS_TMP = tempfile.mkdtemp(prefix="estante-tests-")
atexit.register(shutil.rmtree, _LIVROS_TMP, True)
os.environ["LIVROS_DIR"] = _LIVROS_TMP
os.environ["LIB_PSWD"] = "teste"

import app as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def isolar_estado(tmp_path, monkeypatch):
    """Cada teste usa cache de capas próprio e começa sem falhas de login,
    para não tocar em .cache real nem vazar bloqueio entre testes."""
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    monkeypatch.setattr(app_module, "COVERS_DIR", covers_dir)
    monkeypatch.setattr(app_module, "INDEX_FILE", tmp_path / "index.json")
    with app_module._falhas_lock:
        app_module._falhas_login.clear()
    yield
    with app_module._falhas_lock:
        app_module._falhas_login.clear()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c
