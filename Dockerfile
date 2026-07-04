FROM python:3.11-slim

WORKDIR /app

# libpq-dev → psycopg2 | libgomp1 → TensorFlow OpenMP | gcc → compilación C
RUN apt-get update && apt-get install -y \
    libpq-dev \
    libgomp1 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Archivos estáticos en build-time (SECRET_KEY dummy solo para collectstatic)
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8080

# Comando por defecto (fly.toml lo sobreescribe vía [processes])
CMD ["gunicorn", "core.wsgi:application", "--workers", "2", "--timeout", "120", "--bind", "0.0.0.0:8080"]
