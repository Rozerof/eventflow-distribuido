import os
import json
import uuid
from typing import Optional, List

import pika
import redis
from redis.exceptions import LockError
import psycopg2
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

# --- Configuración ---
NODE_ID = os.getenv("NODE_ID", "N/A")
DB_HOST = os.getenv("DB_HOST", "db")
REDIS_HOST = os.getenv("REDIS_HOST", "cache")
# 👈 CORRECCIÓN AÑADIDA: Leer credenciales de DB
DB_USER = os.environ.get("DB_USER", "user") 
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_NAME = os.environ.get("DB_NAME", "eventflow_db")
# -------------------------------------
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "queue")

# --- Configuración de Seguridad (debe coincidir con el servicio de autenticación) ---
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_secret_key_for_dev")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(
    title=f"EventFlow Node {NODE_ID}",
    description="Backend para gestión de eventos con resiliencia de lectura/escritura.",
    version="1.0.0"
)

# Instrumentación para Prometheus
Instrumentator().instrument(app).expose(app)

# --- Modelos ---
class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None

class User(BaseModel):
    id: int
    username: str

# --- Dependencia de Autenticación ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        if username is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(username=username, user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    return User(id=token_data.user_id, username=token_data.username)

# --- Conexiones a Servicios ---
def get_redis_connection():
    return redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

def get_db_connection():
    """
    Intenta conectar a la BD usando las variables de entorno.
    """
    try:
        # Asegúrate de que las variables de entorno se lean correctamente
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME, # 👈 CORREGIDO: Uso de variable de entorno
            user=DB_USER, # 👈 CORREGIDO: Uso de variable de entorno
            password=DB_PASSWORD, # 👈 CORREGIDO: Uso de variable de entorno
            host=DB_HOST,
            port=os.getenv("DB_PORT", "5432")
        )
        return conn
    except psycopg2.OperationalError:
        # Si la conexión falla, devuelve None para que los endpoints puedan manejarlo
        print(f"DB CONNECTION ERROR: Failed to connect to PostgreSQL: {e}")
        return None

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": f"Hello from Node {NODE_ID}"}

@app.get("/events/{event_id}")
def read_event(event_id: int):
    redis_conn = get_redis_connection()
    cache_key = f"event:{event_id}"

    cached_event = redis_conn.get(cache_key)
    if cached_event:
        return {"source": "cache", "event": json.loads(cached_event)}

    db_conn = get_db_connection()
    if not db_conn:
        raise HTTPException(status_code=503, detail="Database connection is down and cache is empty (miss).")

    cursor = db_conn.cursor()
    cursor.execute("SELECT id, name, description, date FROM events WHERE id = %s", (event_id,))
    event = cursor.fetchone()
    db_conn.close()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event_data = {"id": event[0], "name": event[1], "description": event[2], "date": event[3].isoformat()}
    redis_conn.set(cache_key, json.dumps(event_data), ex=3600)

    return {"source": "db", "event": event_data}

@app.get("/events/{event_id}/seats")
def get_seat_map(event_id: int):
    db_conn = get_db_connection()
    if not db_conn:
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    
    cursor = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT seat_id, status FROM seats WHERE event_id = %s", (event_id,))
    seats = cursor.fetchall()
    db_conn.close()

    if not seats:
        raise HTTPException(status_code=404, detail="Seat map for this event not found.")

    return {"seat_map": seats}

class LockRequest(BaseModel):
    event_id: int
    seats: List[str]
    user_id: int

@app.post("/seats/lock")
def lock_seats(request: LockRequest, current_user: User = Depends(get_current_user)):
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="User ID mismatch.")

    redis_conn = get_redis_connection()
    lock_id = f"lock:{uuid.uuid4()}"
    lock_duration = 300  # 5 minutos

    # Usar una transacción de Redis para asegurar la atomicidad
    pipe = redis_conn.pipeline()
    for seat_id in request.seats:
        # Intentar adquirir un bloqueo para cada asiento
        # nx=True asegura que solo se establece si no existe
        pipe.set(f"lock:event:{request.event_id}:seat:{seat_id}", lock_id, ex=lock_duration, nx=True)
    
    results = pipe.execute()

    # Si algún asiento no se pudo bloquear (alguien más lo tomó)
    if not all(results):
        # Intentar liberar los asientos que sí se lograron bloquear
        for i, seat_id in enumerate(request.seats):
            if results[i]:
                redis_conn.delete(f"lock:event:{request.event_id}:seat:{seat_id}")
        raise HTTPException(status_code=409, detail="Some seats are already locked by another user.")

    # Guardar la información del bloqueo
    redis_conn.set(lock_id, json.dumps({"user_id": current_user.id, "seats": request.seats, "event_id": request.event_id}), ex=lock_duration)

    return {"lock_id": lock_id, "expires_in": lock_duration}

class PurchaseRequest(BaseModel):
    lock_id: str
    user_id: int
    event_id: int

@app.post("/purchase", status_code=status.HTTP_202_ACCEPTED)
def confirm_purchase(request: PurchaseRequest, current_user: User = Depends(get_current_user)):
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="User ID mismatch.")

    redis_conn = get_redis_connection()
    lock_data_str = redis_conn.get(request.lock_id)

    if not lock_data_str:
        raise HTTPException(status_code=404, detail="Your seat reservation has expired or is invalid.")

    lock_data = json.loads(lock_data_str)
    if lock_data["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="This lock does not belong to you.")

    # Preparar el mensaje para la cola
    transaction_id = str(uuid.uuid4())
    purchase_message = {
        "transaction_id": transaction_id,
        "user_id": current_user.id,
        "event_id": request.event_id,
        "seats": lock_data["seats"]
    }
    
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='purchase_queue', durable=True)
        channel.basic_publish(
            exchange='', 
            routing_key='purchase_queue', 
            body=json.dumps(purchase_message), 
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()

        # Una vez encolado, eliminar el bloqueo de Redis
        redis_conn.delete(request.lock_id)
        for seat_id in lock_data["seats"]:
            redis_conn.delete(f"lock:event:{request.event_id}:seat:{seat_id}")

        return {"status": "Purchase processing", "transaction_id": transaction_id}
    except pika.exceptions.AMQPConnectionError:
        raise HTTPException(status_code=503, detail="Message queue is not available.")