import time
from fastapi import FastAPI
import prometheus_fastapi_instrumentator

# 1. Crear la aplicación FastAPI
app = FastAPI(title="Microservicio Consumidor de Compras")

# 2. Instrumentar la aplicación para Prometheus
# Esto crea un endpoint /metrics automáticamente
prometheus_fastapi_instrumentator.Instrumentator().instrument(app).expose(app)

@app.get("/")
def health_check():
    """Endpoint de salud para verificar que el servicio está vivo."""
    return {"status": "ok", "service": "ms-consumer"}

# Aquí iría la lógica para conectarse a RabbitMQ y consumir mensajes.
# Por ahora, el servicio solo se levantará y expondrá métricas.