import os
import psycopg2
from fastapi import FastAPI, HTTPException
import uvicorn
import time

# --- Configuración del Entorno ---
DB_HOST = os.environ.get("DB_HOST", "db")

app = FastAPI(
    title="Microservicio de Análisis de Eventos",
    description="Proporciona métricas y consultas pesadas leyendo de PostgreSQL.",
    version="1.0.0"
)

# Función para obtener la conexión a PostgreSQL
def get_db_connection():
    # ... (código de conexión) ...
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database="eventflow_db",
            user="user",
            password="password",
            connect_timeout=3
        )
        return conn
    except Exception as e:
        print(f"ANÁLISIS ERROR: Falló la conexión a PostgreSQL: {e}")
        return None

# Endpoint para la Consulta Crítica (Simulación de consulta pesada)
@app.get("/metrics/sales-summary")
def get_sales_summary():
    # ... (código de simulación de consulta) ...
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="Database connection required for analysis.")

    try:
        # Simulamos una consulta compleja que toma 2 segundos de CPU
        time.sleep(2) 
        
        # Datos simulados:
        data = {
            "total_events": 1,
            "total_tickets_sold": 50,
            "total_revenue": 5000.00,
            "processing_node": "MS2",
            "timestamp": time.time()
        }
        
        conn.close()
        
        return data

    except Exception as e:
        print(f"ANÁLISIS CRÍTICO: Error durante la consulta: {e}")
        raise HTTPException(status_code=500, detail="Internal analysis processing error.")

# Health Check
@app.get("/health")
def health_check():
    return {"status": "ok"}