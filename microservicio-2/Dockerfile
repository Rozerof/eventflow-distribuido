# Usa una imagen base ligera de Python
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código del microservicio
COPY src /app/src

# Comando para correr la API de Análisis (Servidor Web Uvicorn/FastAPI)
CMD ["uvicorn", "src.analysis_app:app", "--host", "0.0.0.0", "--port", "8001"]
