from scanner import clean_title, scan_library


def test_clean_title_transforma_nome_de_arquivo():
    assert clean_title("dom_casmurro-1899.epub") == "Dom Casmurro 1899"


def test_clean_title_vazio_vira_sem_titulo():
    assert clean_title("") == "Sem título"
    assert clean_title("___.pdf") == "Sem título"


def _montar_biblioteca(raiz):
    (raiz / "Machado de Assis").mkdir()
    (raiz / "Machado de Assis" / "sub").mkdir()
    (raiz / "Machado de Assis" / "dom_casmurro-1899.epub").write_bytes(b"x")
    (raiz / "Machado de Assis" / "sub" / "memorias.pdf").write_bytes(b"x")
    (raiz / "solto.txt").write_bytes(b"x")          # raiz -> Desconhecido
    (raiz / "Autor X").mkdir()
    (raiz / "Autor X" / "notas.xyz").write_bytes(b"x")  # extensão não suportada
    (raiz / "Autor X" / "CAPS.EPUB").write_bytes(b"x")  # extensão em maiúscula
    (raiz / ".oculta").mkdir()
    (raiz / ".oculta" / "secreto.epub").write_bytes(b"x")  # pasta oculta
    (raiz / "Autor X" / ".cache").mkdir()
    (raiz / "Autor X" / ".cache" / "escondido.epub").write_bytes(b"x")


def test_scan_library_autor_extensoes_e_ocultos(tmp_path):
    _montar_biblioteca(tmp_path)

    livros = scan_library(str(tmp_path))
    pares = {(b.author, b.title) for b in livros}

    assert pares == {
        ("Machado de Assis", "Dom Casmurro 1899"),
        ("Machado de Assis", "Memorias"),
        ("Desconhecido", "Solto"),
        ("Autor X", "Caps"),
    }
    assert {b.ext for b in livros} == {"epub", "pdf", "txt"}


def test_scan_library_pasta_inexistente_retorna_lista_vazia(tmp_path):
    assert scan_library(str(tmp_path / "nao-existe")) == []
