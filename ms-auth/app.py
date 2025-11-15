import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.pool import SimpleConnectionPool
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import sys

# --- Configuration ---
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "eventflow_db")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Database Connection Pool ---
db_pool = None 
try:
    print(f"INFO: Intentando conectar a DB en: {DB_HOST}:{DB_PORT}/{DB_NAME} con usuario: {DB_USER}")
    # Crea un pool de conexiones en lugar de conexiones individuales.
    db_pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
    print("INFO: Pool de conexión a la base de datos inicializado exitosamente.")
except Exception as e:
    # Capturamos cualquier error de conexión
    print("-" * 50)
    print(f"CRITICAL ERROR: Falló la inicialización del pool de conexión a la base de datos.")
    print(f"Error de PostgreSQL: {e}")
    print(f"Cadena de conexión intentada (DSN): {DATABASE_URL}")
    print("-" * 50)
    sys.exit(1)


SECRET_KEY = "a_very_secret_key"
ALGORITHM = "HS256" 
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ** CORRECCIÓN CLAVE: Forzar el back-end CFFI de passlib para evitar el AttributeError **
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__using='cryptography')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

app = FastAPI()

# --- CORS Middleware ---
origins = ["*"] 
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Connection ---
def get_db_connection():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


# --- Models ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str
class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str

# --- Security Functions ---

# Constante que define el límite de bytes de bcrypt
BCRYPT_MAX_BYTES = 72

def get_truncated_password(password: str) -> str: 
    """
    Trunca la contraseña a 72 bytes (el límite de bcrypt) para evitar ValueError.
    """
    # Codifica la contraseña en bytes
    password_bytes = password.encode('utf-8')
    
    # Si la longitud excede el límite de bcrypt
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        # Trunca los bytes y decodifica de nuevo a string (ignorando errores)
        print(f"WARNING: Contraseña truncada de {len(password_bytes)} bytes a {BCRYPT_MAX_BYTES} bytes.")
        return password_bytes[:BCRYPT_MAX_BYTES].decode('utf-8', errors='ignore')
    
    return password

def verify_password(plain_password, hashed_password):
    # CORRECCIÓN: Trunca la contraseña de entrada antes de verificarla.
    plain_password = get_truncated_password(plain_password)
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    # CORRECCIÓN: Trunca la contraseña antes de hashearla para evitar el error
    password = get_truncated_password(password)
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Endpoints ---
@app.post("/signup", status_code=status.HTTP_201_CREATED, response_model=Token)
def signup(user: UserCreate, conn: any = Depends(get_db_connection)):
    try:
        hashed_password = get_password_hash(user.password)
    except Exception as e:
        # La corrección del código sigue aquí, pero ahora la excepción debería ser evitada.
        print(f"ERROR al hashear la contraseña: {e}")
        raise HTTPException(status_code=500, detail="Error en el procesamiento de la contraseña")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, email, hashed_password) VALUES (%s, %s, %s) RETURNING id, username",
                (user.username, user.email, hashed_password)
            )
            new_user = cursor.fetchone()
            conn.commit()
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    user_id, username = new_user
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": username, "user_id": user_id}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer", "user_id": user_id, "username": username}

@app.post("/login", response_model=Token)
def login(user_login: UserLogin, conn: any = Depends(get_db_connection)):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM users WHERE username = %s", (user_login.username,))
        user = cursor.fetchone()

    if not user or not verify_password(user_login.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user_id": user["id"], "username": user["username"]}