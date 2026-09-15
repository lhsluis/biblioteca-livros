FROM python:3.12-slim

# fonts-dejavu-core: usada pelo cover_extractor.py para desenhar as capas
# ilustradas (título/autor) dos livros sem capa embutida. Sem isso, o
# Pillow cai no fallback de bitmap feio do ImageFont.load_default().
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core curl\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && mkdir -p /data/livros /app/.cache \
    && chown -R appuser:appuser /app /data/livros
USER appuser

ENV PYTHONUNBUFFERED=1 \
    LIVROS_DIR=/data/livros

EXPOSE 5000

# Um único worker de propósito: build_library() lê/escreve o cache de capas
# (.cache/index.json) e a chave de sessão (.cache/secret.key) em disco sem
# nenhum lock. Com mais de um worker, cada processo escaneia a biblioteca
# de forma independente e pode haver corrida na escrita desses arquivos.
# Para mais concorrência, prefira "--threads" a "--workers".
CMD ["python3", "-m", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
