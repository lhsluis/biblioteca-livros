"""
cover_extractor.py
-------------------
Obtém uma imagem de capa para cada livro:

1. EPUB  -> lê o container.xml + OPF e extrai a imagem de capa real.
2. PDF   -> renderiza a primeira página com PyMuPDF.
3. DOCX  -> usa a primeira imagem embutida em word/media (heurística).
4. Outros (doc, txt, mobi, azw3, rtf, odt, fb2) ou falha na extração
   -> gera uma capa ilustrada com título/autor/formato.
"""

import io
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COVER_W, COVER_H = 400, 600

# Paleta inspirada em couro, papel envelhecido e latão de biblioteca antiga,
# usada apenas como base para o degradê de cada capa gerada.
PALETTE = [
    ("#2B1B17", "#5C3A2E"),
    ("#1F2A24", "#3E5C4E"),
    ("#241E33", "#4B3B6B"),
    ("#2E2419", "#6B4F2A"),
    ("#1A2634", "#3A5570"),
    ("#331E22", "#6E3B3F"),
    ("#20242B", "#4A4E5A"),
    ("#2A1F3D", "#6A3E5C"),
]


def _pick_colors(seed: str):
    idx = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % len(PALETTE)
    return PALETTE[idx]


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def generate_placeholder(title: str, author: str, ext: str) -> bytes:
    """Cria uma capa ilustrada quando não há imagem real disponível."""
    c1, c2 = _pick_colors(title + author)
    from_rgb = tuple(int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    to_rgb = tuple(int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    img = Image.new("RGB", (COVER_W, COVER_H), from_rgb)
    pixels = img.load()
    for y in range(COVER_H):
        t = y / COVER_H
        r = int(from_rgb[0] + (to_rgb[0] - from_rgb[0]) * t)
        g = int(from_rgb[1] + (to_rgb[1] - from_rgb[1]) * t)
        b = int(from_rgb[2] + (to_rgb[2] - from_rgb[2]) * t)
        for x in range(COVER_W):
            pixels[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img)

    # moldura fina, como a lombada de um livro encadernado
    draw.rectangle([14, 14, COVER_W - 14, COVER_H - 14], outline=(212, 186, 130), width=2)

    title_font = _font(32, bold=True)
    author_font = _font(20)
    badge_font = _font(15)

    lines = _wrap_text(draw, title, title_font, COVER_W - 90)[:6]
    total_h = len(lines) * 42
    y = (COVER_H - total_h) // 2 - 20
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((COVER_W - w) / 2, y), line, font=title_font, fill=(240, 232, 214))
        y += 42

    a_bbox = draw.textbbox((0, 0), author, font=author_font)
    aw = a_bbox[2] - a_bbox[0]
    draw.text(((COVER_W - aw) / 2, COVER_H - 100), author, font=author_font, fill=(212, 186, 130))

    badge = ext.upper()
    b_bbox = draw.textbbox((0, 0), badge, font=badge_font)
    bw, bh = b_bbox[2] - b_bbox[0], b_bbox[3] - b_bbox[1]
    pad = 8
    draw.rectangle(
        [COVER_W - bw - pad * 2 - 24, 24, COVER_W - 24, 24 + bh + pad * 2],
        fill=(0, 0, 0),
    )
    draw.text((COVER_W - bw - pad - 24, 24 + pad), badge, font=badge_font, fill=(240, 232, 214))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def extract_epub_cover(path: str):
    """Extrai a imagem de capa real declarada dentro do EPUB, se houver."""
    try:
        with zipfile.ZipFile(path) as z:
            container = z.read("META-INF/container.xml")
            root = ET.fromstring(container)
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            opf_path = root.find(".//c:rootfile", ns).attrib["full-path"]
            opf_dir = str(Path(opf_path).parent)
            opf_root = ET.fromstring(z.read(opf_path))
            ns_opf = {"opf": "http://www.idpf.org/2007/opf"}

            cover_id = None
            for meta in opf_root.findall(".//opf:metadata/opf:meta", ns_opf):
                if meta.attrib.get("name") == "cover":
                    cover_id = meta.attrib.get("content")
                    break

            manifest = opf_root.findall(".//opf:manifest/opf:item", ns_opf)
            href = None

            if cover_id:
                for item in manifest:
                    if item.attrib.get("id") == cover_id:
                        href = item.attrib.get("href")
                        break
            if not href:
                for item in manifest:
                    if "cover-image" in item.attrib.get("properties", ""):
                        href = item.attrib.get("href")
                        break
            if not href:
                for item in manifest:
                    if ("cover" in item.attrib.get("id", "").lower()
                            and item.attrib.get("media-type", "").startswith("image/")):
                        href = item.attrib.get("href")
                        break

            if href:
                img_path = href if opf_dir in ("", ".") else f"{opf_dir}/{href}"
                img_path = img_path.replace("//", "/")
                return z.read(img_path)
    except Exception:
        return None
    return None


def extract_pdf_cover(path: str):
    """Renderiza a primeira página do PDF como imagem de capa."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("jpg")
        doc.close()
        return img_bytes
    except Exception:
        return None


def extract_docx_image(path: str):
    """Heurística: usa a primeira imagem embutida no .docx como pseudo-capa."""
    try:
        with zipfile.ZipFile(path) as z:
            media = sorted(n for n in z.namelist() if n.startswith("word/media/"))
            if not media:
                return None
            return z.read(media[0])
    except Exception:
        return None


def normalize_image(data: bytes):
    """Garante formato/tamanho consistentes para qualquer imagem extraída."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((COVER_W, COVER_H * 2))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


def get_cover_bytes(book) -> bytes:
    """Ponto de entrada: devolve os bytes JPEG da capa final do livro."""
    data = None
    if book.ext == "epub":
        data = extract_epub_cover(book.path)
    elif book.ext == "pdf":
        data = extract_pdf_cover(book.path)
    elif book.ext == "docx":
        data = extract_docx_image(book.path)

    if data:
        normalized = normalize_image(data)
        if normalized:
            return normalized

    return generate_placeholder(book.title, book.author, book.ext)
