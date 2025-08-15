FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libolm-dev \
    libsqlite3-dev \
    libssl-dev \
    libffi-dev \
    build-essential \
    ffmpeg \
    qrencode \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/downloads /app/static

EXPOSE 10000

CMD ["python", "app.py"]