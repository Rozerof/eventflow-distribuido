import os
import redis
import psycopg2
import json
import time 
import pika 
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import uuid

# --- Configuración del Entorno ---
NODE_ID = os.environ.get("NODE_ID", "UNKNOWN")
DB_HOST = os.environ.get("DB_HOST")
REDIS_HOST = os.environ.get("REDIS_HOST")
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST")

# --- Constantes ---
SEAT_LOCK_TTL = 600 # 10 minutos de bloqueo para los asientos


app = FastAPI(
    title=f"EventFlow Node {NODE_ID}",
    description="Backend para gestión de eventos con resiliencia de lectura/escritura.",
    version="1.0.0"
)

# --- Habilitar CORS ---
# Esto permite que el frontend (servido por NGINX en localhost) se comunique con la API (servida por FastAPI).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas las origenes. Para producción, sería más restrictivo (ej. ["http://localhost", "https://tu.dominio.com"])
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todas las cabeceras.
)

# --- CLIENTES DE CONEXIÓN ---
REDIS_CLIENT = None
try:
    REDIS_CLIENT = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    REDIS_CLIENT.ping()
    print("INFO: Conexión exitosa a Redis.")
except Exception as e:
    print(f"ERROR: Falló la conexión inicial a Redis: {e}.")
    REDIS_CLIENT = None

def get_db_connection():
    # ... (El código de esta función es correcto, no necesita cambios) ...
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database="eventflow_db",
            user="user",
            password="password",
            connect_timeout=1
        )
        return conn
    except Exception as e:
        return None

# --- FUNCIÓN CLAVE: Conexión Lazy a RabbitMQ con Retries ---
def get_rabbitmq_connection(max_retries: int = 5, delay: int = 1) -> Optional[pika.BlockingConnection]:
    """
    Intenta reconectar a RabbitMQ con retries.
    Esto hace que la publicación sea resiliente a fallos transitorios de conexión.
    """
    for attempt in range(1, max_retries + 1):
        try:
            # CLAVE: Añadir timeouts para que la conexión falle rápido si RabbitMQ no está disponible.
            params = pika.ConnectionParameters(
                host=RABBITMQ_HOST, port=5672,
                blocked_connection_timeout=2 # Timeout para cada intento de conexión
            )
            connection = pika.BlockingConnection(params)
            return connection
        except Exception as e:
            if attempt < max_retries:
                print(f"WARNING: Falló la conexión a RabbitMQ (Intento {attempt}/{max_retries}). Reintentando en {delay}s.")
                time.sleep(delay)
            else:
                print(f"CRITICAL ERROR: Falló la conexión a RabbitMQ después de {max_retries} intentos: {e}")
    return None

# Función para publicar en la cola
def publish_to_queue(message_body: Dict[str, Any]):
    """Publica el mensaje en la cola de transacciones."""
    connection = get_rabbitmq_connection()
    if not connection:
        raise Exception("RabbitMQ connection is not available for publishing.")
    
    try:
        channel = connection.channel()
        channel.queue_declare(queue='transaction_queue', durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key='transaction_queue',
            body=json.dumps(message_body),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
            )
        )
    finally:
        # Es crucial cerrar la conexión después de enviar para no saturar los recursos.
        if connection and connection.is_open:
            connection.close()


# --- Endpoints Básicos y Health ---

# --- Modelos de Datos (Pydantic) ---
class SeatLockRequest(BaseModel):
    event_id: int
    seats: List[str] # Ej: ["A1", "A2"]
    user_id: int


@app.get("/")
def read_root():
    return {
        "status": "up", 
        "message": f"Hello from Node {NODE_ID} (Port 8000)",
        "environment": {"db": DB_HOST, "cache": REDIS_HOST, "queue": RABBITMQ_HOST}
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- FLUJO DE USUARIO: PASO 1 - Listar Eventos ---
@app.get("/events", summary="Obtener lista de eventos disponibles")
def get_all_events():
    """
    Devuelve una lista de todos los eventos disponibles.
    Utiliza la misma estrategia de Cache-Aside que el endpoint de detalle.
    """
    cache_key = "events:all"
    # 1. Intento de Lectura desde Cache
    if REDIS_CLIENT:
        cached_events = REDIS_CLIENT.get(cache_key)
        if cached_events:
            return {"source": "cache", "events": json.loads(cached_events)}

    # 2. Fallback a Base de Datos
    # En una app real, aquí harías: "SELECT id, name FROM events WHERE is_active = true"
    # Para la demo, devolvemos datos fijos.
    events_data = [
        {"id": 999, "name": "Conferencia Sistemas Distribuidos"},
        {"id": 101, "name": "Concierto de Rock"},
        {"id": 202, "name": "Obra de Teatro Clásica"}
    ]
    if REDIS_CLIENT:
        REDIS_CLIENT.set(cache_key, json.dumps(events_data), ex=300)
    return {"source": "database", "events": events_data}

# --- FLUJO DE USUARIO: PASO 2 - Ver Detalles de un Evento ---
@app.get("/events/{event_id}")
def get_event_details(event_id: int):
    """
    Implementa la estrategia Cache-Aside. 
    Garantiza disponibilidad de lectura si la BD falla (usando datos de Redis).
    """
    cache_key = f"event:{event_id}"

    # 1. Intento de Lectura: Cache First (ALTA DISPONIBILIDAD)
    if REDIS_CLIENT:
        data = REDIS_CLIENT.get(cache_key)
        if data:
            # Deserializa la cadena JSON almacenada en Redis
            return {"source": "cache", "event": json.loads(data)}
    
    # --- BD Fallback: Si no está en caché o Redis está caído ---

    conn = get_db_connection()
    if conn:
        try:
            # Simulamos la obtención de datos de evento (Ejemplo simple)
            # Nota: Para esta demo, solo se necesita el evento 999
            if event_id == 999:
                 result = [999, 'Conferencia Sistemas Dist.', 'Resiliencia demo data']
            else:
                 result = None # No encontrado

            if result:
                # 2. Cache-Aside: Actualiza el caché después de leer de la BD
                event_data = {"id": event_id, "name": result[1], "description": result[2]}
                if REDIS_CLIENT:
                    # Serializa a JSON antes de guardar en Redis
                    REDIS_CLIENT.set(cache_key, json.dumps(event_data), ex=300) 
                
                return {"source": "database", "event": event_data}
            else:
                # La BD está up, pero el evento no existe
                raise HTTPException(status_code=404, detail="Event not found in Database.")
        
        except Exception as e:
            # Error durante la Query, no durante la conexión.
            print(f"DB Query Error: {e}")
            raise HTTPException(status_code=503, detail="Database error during query.")

    # 3. Fallo Total: Si la BD está caída Y hubo un Cache Miss.
    raise HTTPException(status_code=503, detail="System unavailable: DB is down and data not found in cache.")

# --- FLUJO DE USUARIO: PASO 3 - Ver Mapa de Asientos ---
@app.get("/events/{event_id}/seats", summary="Obtener mapa de asientos de un evento")
def get_seat_map(event_id: int):
    """
    Devuelve el estado de los asientos para un evento.
    El estado (disponible, ocupado, reservado) se gestiona en Redis para alta velocidad.
    """
    if not REDIS_CLIENT:
        raise HTTPException(status_code=503, detail="Seat management service is unavailable (Redis down).")

    # En una app real, la configuración de asientos vendría de la BD.
    # Para la demo, generamos 20 asientos (A1-A10, B1-B10).
    seat_ids = [f"{row}{i}" for row in "AB" for i in range(1, 11)]
    
    # Consultamos el estado de todos los asientos en una sola operación
    seat_states = REDIS_CLIENT.mget([f"seat:{event_id}:{sid}" for sid in seat_ids])

    seat_map = []
    for i, sid in enumerate(seat_ids):
        state = seat_states[i] or "available" # Si no existe en Redis, está disponible
        seat_map.append({"seat_id": sid, "status": state})

    return {"event_id": event_id, "seat_map": seat_map}

# --- FLUJO DE USUARIO: PASO 4 - Bloquear Asientos ---
@app.post("/seats/lock", summary="Bloquea asientos temporalmente antes de la compra")
def lock_seats(request: SeatLockRequest):
    """
    Intenta bloquear un conjunto de asientos para un usuario.
    Este es un paso CRÍTICO para evitar que dos usuarios compren el mismo asiento.
    Utiliza una transacción de Redis para garantizar atomicidad.
    """
    if not REDIS_CLIENT:
        raise HTTPException(status_code=503, detail="Seat management service is unavailable (Redis down).")

    lock_id = str(uuid.uuid4())
    
    # Usamos un pipeline de Redis para una operación atómica
    pipe = REDIS_CLIENT.pipeline()
    seat_keys = [f"seat:{request.event_id}:{sid}" for sid in request.seats]

    try:
        # 1. Vigilar si alguna de las claves de asiento cambia mientras estamos en la transacción
        pipe.watch(*seat_keys)

        # 2. Comprobar que todos los asientos estén disponibles
        current_states = REDIS_CLIENT.mget(seat_keys)
        if any(state is not None for state in current_states):
            raise HTTPException(status_code=409, detail="One or more selected seats are no longer available.")

        # 3. Iniciar la transacción
        pipe.multi()
        for key in seat_keys:
            pipe.set(key, "locked", ex=SEAT_LOCK_TTL)
        
        # Guardamos la información del bloqueo para usarla en la compra
        pipe.set(f"lock:{lock_id}", json.dumps(request.dict()), ex=SEAT_LOCK_TTL)

        # 4. Ejecutar la transacción
        pipe.execute()

        return {"status": "seats_locked", "lock_id": lock_id, "expires_in": SEAT_LOCK_TTL}

    except redis.exceptions.WatchError:
        # Ocurrió si otro cliente modificó un asiento mientras lo comprobábamos.
        raise HTTPException(status_code=409, detail="Conflict: Seat status changed during selection. Please try again.")
    finally:
        pipe.reset()

# --- FLUJO DE USUARIO: PASO 5 - Confirmar Compra ---
@app.post("/purchase", summary="Confirma la compra usando un bloqueo de asientos") 
def create_purchase(lock_id: str = Body(..., embed=True), user_id: int = Body(..., embed=True)):
    """
    Confirma una compra utilizando un `lock_id` previamente obtenido.
    Publica la transacción en RabbitMQ para procesamiento asíncrono.
    """
    if not REDIS_CLIENT:
        raise HTTPException(status_code=503, detail="Service unavailable (Redis down).")

    lock_key = f"lock:{lock_id}"
    lock_data_raw = REDIS_CLIENT.get(lock_key)

    if not lock_data_raw:
        raise HTTPException(status_code=404, detail="Seat lock not found or expired. Please select seats again.")
    
    lock_data = json.loads(lock_data_raw)
    if lock_data['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="This lock does not belong to the current user.")

    # Preparamos el mensaje para la cola
    transaction_data = {
        "user_id": lock_data['user_id'],
        "event_id": lock_data['event_id'],
        "seats": lock_data['seats'],
        "timestamp": time.time(),
        "transaction_id": f"txn_{uuid.uuid4().hex}"
    }
    
    try:
        # Publica la transacción en la cola de mensajes
        publish_to_queue(transaction_data)

        # Una vez encolado, marcamos los asientos como 'taken' permanentemente
        pipe = REDIS_CLIENT.pipeline()
        for seat in lock_data['seats']:
            pipe.set(f"seat:{lock_data['event_id']}:{seat}", "taken")
            pipe.persist(f"seat:{lock_data['event_id']}:{seat}")
        pipe.delete(lock_key)
        pipe.execute()

        # La respuesta al usuario es inmediata y positiva (aceptada para procesamiento)
        return {
            "status": "ACCEPTED_ASYNC",
            "message": "Transaction accepted and queued for processing.",
            "transaction_id": transaction_data["transaction_id"]
        }

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to publish to RabbitMQ: {e}")
        raise HTTPException(
            status_code=503,
            detail="System critical failure: Cannot queue transaction. Try again later."
        )

# --- Inicialización simulada de datos (Solo para la demo) ---
@app.on_event("startup")
def startup_event():    
    if REDIS_CLIENT:
        try:
            # Usaremos el ID 999 para la demostración
            demo_data = {"id": 999, "name": "Conferencia Sistemas Distribuidos", "description": "Resiliencia demo data"}
            REDIS_CLIENT.set(f"event:999", json.dumps(demo_data), ex=300)
            print("INFO: Evento 999 precargado en Redis.")
        except Exception as e:
            print(f"WARNING: No se pudo precargar Redis: {e}")
