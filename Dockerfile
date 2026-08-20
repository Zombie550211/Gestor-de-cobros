FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# PyPI devuelve 502 intermitentes y tumba el build. Los --retries de pip solo cubren
# un paquete a la vez, asi que reintentamos el lote completo con esperas crecientes.
# Conservamos la cache entre intentos (para no rebajar lo ya descargado) y la
# borramos al final para no engordar la imagen.
RUN pip install --no-cache-dir --upgrade pip \
 && for i in 1 2 3 4 5; do \
      pip install --retries 10 --timeout 60 -r requirements.txt && break; \
      if [ "$i" = 5 ]; then echo ">> pip fallo tras 5 intentos" >&2; exit 1; fi; \
      echo ">> pip fallo (intento $i/5); reintentando en $((i * 15))s..." >&2; \
      sleep $((i * 15)); \
    done \
 && pip cache purge
COPY . .
EXPOSE 8000
# Render (y otros hosts) asignan el puerto por la variable $PORT; usamos 8000 como respaldo local
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
