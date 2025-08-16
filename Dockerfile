FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias (añadimos procps para monitoreo)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Puerto ficticio para Render
EXPOSE 10000

CMD ["python", "app.py"]