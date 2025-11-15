# Usamos una imagen slim para reducir el tamaño
FROM python:3.11-slim

# 1. Instalar dependencias de compilación y librerías nativas requeridas:
#    - build-essential, gcc: Necesarios para compilar bcrypt.
#    - libpq-dev: Necesario para que psycopg2 pueda conectarse a PostgreSQL.
#    - python3-dev, libffi-dev: Necesario para headers de Python y compilación de librerías.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        python3-dev \
        libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo
WORKDIR /app

# 2. Copiar e instalar dependencias de Python
COPY requirements.txt .
# Aseguramos que la instalación se haga con las dependencias de compilación
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiar el código de la aplicación y ejecutar el servidor
COPY . .

# Exponer el puerto
EXPOSE 8001

# Comando de inicio
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
