# Usa una imagen base ligera de Python
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código del microservicio (el consumidor)
COPY src /app/src

# Comando para correr el consumidor de la cola (script de Python)
CMD ["python", "src/consumer.py"]