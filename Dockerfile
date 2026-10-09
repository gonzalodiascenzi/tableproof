# servidor de venta de un emprendimiento. uso:
#   docker build -t tableproof .
#   docker run -p 8080:8080 --env-file .env -e VENTURE=<slug> -e DB_PATH=/data/tableproof.sqlite -v tableproof-data:/data tableproof
# para productos de descarga, montá también ventures/<slug>/entrega/ (el archivo no se commitea).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV HOST=0.0.0.0 PORT=8080
CMD ["sh", "-c", "python -m engine.app ventures/${VENTURE:?definí VENTURE con el slug del emprendimiento} --db ${DB_PATH:-/data/tableproof.sqlite}"]
