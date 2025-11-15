# microservicio-1/src/consumer.py
import pika
import time
import json
import os
import psycopg2 

# OBTENER LAS VARIABLES DE ENTORNO DE DOCKER-COMPOSE
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "queue")
DB_HOST = os.environ.get("DB_HOST", "db")
DB_USER = os.environ.get("DB_USER", "user") # 👈 CORRECCIÓN: Leer de env
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password") # 👈 CORRECCIÓN: Leer de env
DB_NAME = os.environ.get("DB_NAME", "eventflow_db") # 👈 CORRECCIÓN: Leer de env

# Excepción personalizada para manejar la caída de la BD
class StopConsumingException(Exception):
    """Excepción lanzada para detener el bucle de consumo actual."""
    pass

# --- Función de Conexión a la BD ---
def get_db_connection():
    """Intenta conectar a la BD con reintentos para esperar a que se recupere."""
    retries = 5
    delay = 3
    for i in range(retries):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME, # 👈 Usar variable de entorno
                user=DB_USER, # 👈 Usar variable de entorno
                password=DB_PASSWORD, # 👈 Usar variable de entorno
                connect_timeout=2 # Un timeout de conexión un poco más largo
            )
            print("CONSUMER INFO: Conexión a la BD exitosa.")
            return conn
        except (psycopg2.OperationalError) as e:
            print(f"CONSUMER WARNING: No se pudo conectar a la BD (Intento {i+1}/{retries}). Reintentando en {delay}s...")
            time.sleep(delay)
    return None

# --- Lógica de Procesamiento de Mensajes ---
def process_message(ch, method, properties, body):
    
    message_data = json.loads(body)
    print(f"CONSUMER INFO: Recibido mensaje para procesar: {message_data['transaction_id']}")

    conn = get_db_connection()

    if conn is None:
        # Si la BD está caída después de los reintentos, hacemos un NACK (Negative Acknowledgement)
        # y devolvemos el mensaje a la cola para que otro consumidor (o este mismo más tarde) lo intente.
        print("CONSUMER CRITICAL: BD caída tras reintentos. Devolviendo mensaje a la cola (NACK).")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
        # Forzamos una pausa para no reintentar el mismo mensaje inmediatamente en un bucle rápido.
        time.sleep(5)
        return # Salimos de esta ejecución de callback

    # Si la BD está activa, escribimos.
    try:
        cursor = conn.cursor()
        
        # Simulamos la escritura de la transacción crítica
        time.sleep(1) 

        # Si la escritura es exitosa, registramos el log
        print(f"CONSUMER SUCCESS: Transacción {message_data['transaction_id']} escrita en BD. Enviando notificación...")
        
        conn.close()
        
        # ACKNOWLEDGEMENT: Solo hacemos ACK si la escritura fue exitosa.
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"CONSUMER CRITICAL ERROR: Falló la escritura en BD: {e}")
        conn.close()
        # En caso de error de procesamiento (ej. query), no hacemos ACK.

# --- Inicialización del Consumidor ---
if __name__ == '__main__':
    while True:
        try:
            # 1. Conexión a RabbitMQ
            params = pika.ConnectionParameters(host=RABBITMQ_HOST, port=5672)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            
            channel.queue_declare(queue='transaction_queue', durable=True)
            channel.basic_qos(prefetch_count=1)
            
            print('CONSUMER INFO: Esperando mensajes. Para salir, presione CTRL+C')
            
            # 2. Configurar Consumo
            channel.basic_consume(
                queue='transaction_queue',
                on_message_callback=process_message
            )
            
            # 3. Empezar a consumir
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            print(f"CONSUMER WARNING: Conexión RabbitMQ perdida ({e}). Reintentando en 5 segundos...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Consumer detenido.")
            break
        except Exception as e:
             # Capturar cualquier otro error y forzar el reintento
            print(f"ERROR Desconocido en el Consumidor: {e}. Reintentando en 5 segundos...")
            time.sleep(5)
        finally:
            # Asegurar que la conexión siempre se cierre para que el bucle while True reintente.
            if 'connection' in locals() and connection.is_open:
                connection.close()