import os
import json
import uuid
from typing import Optional

import pika
import redis
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
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "queue")

# --- Configuración de Seguridad (debe coincidir con el servicio de autenticación) ---
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_secret_key_for_dev")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title=f"EventFlow - Nodo {NODE_ID}")

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
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "eventflow_db"),
            user=os.getenv("DB_USER", "user"),
            password=os.getenv("DB_PASSWORD", "password"),
            host=DB_HOST,
            port=os.getenv("DB_PORT", "5432")
        )
        return conn
    except psycopg2.OperationalError:
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

@app.post("/purchase")
def create_purchase(event_id: int, quantity: int, current_user: User = Depends(get_current_user)):
    transaction_id = str(uuid.uuid4())
    purchase_data = {"transaction_id": transaction_id, "user_id": current_user.id, "event_id": event_id, "quantity": quantity}
    
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='purchase_queue', durable=True)
        channel.basic_publish(exchange='', routing_key='purchase_queue', body=json.dumps(purchase_data), properties=pika.BasicProperties(delivery_mode=2))
        connection.close()
        return {"status": "ACCEPTED_ASYNC", "transaction_id": transaction_id}
    except pika.exceptions.AMQPConnectionError:
        raise HTTPException(status_code=503, detail="Message queue is not available.")