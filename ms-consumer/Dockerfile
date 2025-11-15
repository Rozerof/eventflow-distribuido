# Usa una imagen base de Python
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia e instala las dependencias
# Se copian por separado para aprovechar el cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código de la aplicación
COPY . .

# Comando para ejecutar la aplicación. Expone métricas en el puerto 8001.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]