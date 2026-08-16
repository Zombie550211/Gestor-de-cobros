FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# PyPI devuelve 502 intermitentes y tumba el build: reintentar en vez de fallar.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
      --retries 10 \
      --timeout 60 \
      -r requirements.txt
COPY . .
EXPOSE 8000
# Render (y otros hosts) asignan el puerto por la variable $PORT; usamos 8000 como respaldo local
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
