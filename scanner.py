"""
scanner.py
----------
Percorre recursivamente o diretório da biblioteca e monta uma lista plana
de livros, não importa em qual subpasta cada arquivo esteja.

Regra de autoria: o autor de um livro é o nome da primeira subpasta
dentro do diretório raiz (ex.: Livros/Machado de Assis/dom-casmurro.epub
-> autor = "Machado de Assis"). Arquivos soltos na raiz caem em
"Desconhecido".
"""

import os
import hashlib
from dataclasses import dataclass
from pathlib import Path

# Extensões de e-book/documento que a aplicação reconhece.
SUPPORTED_EXTENSIONS = {
    ".pdf", ".epub", ".txt", ".doc", ".docx",
    ".mobi", ".azw", ".azw3", ".rtf", ".odt", ".fb2",
}


@dataclass
class Book:
    id: str
    title: str
    author: str
    path: str
    ext: str
    size: int
    mtime: float
    cover_url: str = ""


def make_id(path: str) -> str:
    """ID estável baseado no caminho absoluto do arquivo."""
    return hashlib.md5(path.encode("utf-8")).hexdigest()


def clean_title(filename: str) -> str:
    """Transforma 'dom_casmurro-1899.epub' em 'Dom Casmurro 1899'."""
    name = Path(filename).stem
    name = name.replace("_", " ").replace("-", " ").replace(".", " ")
    name = " ".join(name.split())
    return name.strip().title() if name else "Sem título"


def scan_library(root_dir: str):
    """Retorna uma lista de Book, ordenada por autor e depois por título."""
    root = Path(root_dir).expanduser().resolve()
    books = []

    if not root.exists():
        return books

    for dirpath, dirnames, filenames in os.walk(root):
        # ignora pastas ocultas (.git, .cache, etc.)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            full_path = Path(dirpath) / filename
            rel_parent = Path(dirpath).relative_to(root)
            parts = rel_parent.parts
            author = parts[0] if parts else "Desconhecido"

            try:
                stat = full_path.stat()
            except OSError:
                continue

            books.append(
                Book(
                    id=make_id(str(full_path)),
                    title=clean_title(filename),
                    author=author,
                    path=str(full_path),
                    ext=ext.lstrip("."),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )

    books.sort(key=lambda b: (b.author.lower(), b.title.lower()))
    return books
