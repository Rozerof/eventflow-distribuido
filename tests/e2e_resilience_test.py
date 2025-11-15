import subprocess
import requests
import time
import json
import sys

# --- CONFIGURACIÓN DE LA PRUEBA ---
BALANCER_URL = "http://localhost/purchase?user_id=999&event_id=999&quantity=1"
DB_CONTAINER_NAME = "postgres_spof" # Nombre del contenedor para stop/start
CONSUMER_SERVICE_NAME = "ms-notificaciones" # Nombre del servicio para logs
NUM_REQUESTS = 5
REQUEST_TIMEOUT = 30 
WAIT_FOR_RECOVERY = 10 # Tiempo base de espera aumentado para dar margen al consumidor
MAX_RECOVERY_ATTEMPTS = 15 

def run_command(command, check_success=True):
    """Ejecuta comandos de Docker/Shell."""
    try:
        # Usamos check=False para comandos como stop que pueden fallar si el contenedor ya está detenido
        result = subprocess.run(command, shell=True, check=check_success, 
                                capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Esto captura errores donde el comando Docker falla (ej. No such container)
        print(f"ERROR al ejecutar comando: {e.cmd}\nSalida: {e.stderr}")
        return None

def test_e2e_resilience():
    print("--- INICIANDO TEST E2E DE RESILIENCIA ---")
    
    # NUEVO PASO: Limpieza de logs (esto evita que el test use logs viejos)
    print("\n[PREPARACIÓN] Limpiando logs del consumidor...")
    run_command(f"docker-compose stop {CONSUMER_SERVICE_NAME}", check_success=False)
    run_command(f"docker-compose rm -f {CONSUMER_SERVICE_NAME}", check_success=False)
    run_command(f"docker-compose up -d {CONSUMER_SERVICE_NAME}", check_success=True) # Arrancar limpio
    time.sleep(5) # Esperar a que el consumidor intente conectarse a la BD (y muera)


    # 1. Detener la Base de Datos (SPOF)
    print(f"\n1. DETENIENDO SPOF: {DB_CONTAINER_NAME}...")
    run_command(f"docker stop {DB_CONTAINER_NAME}", check_success=False)
    time.sleep(2) 

    # 2. Enviar Transacciones (Escritura Asíncrona)
    print(f"\n2. ENVIANDO {NUM_REQUESTS} TRANSACCIONES (BD CAÍDA)...")
    queued_transactions = 0
    for i in range(NUM_REQUESTS):
        try:
            response = requests.post(BALANCER_URL, timeout=REQUEST_TIMEOUT)
            data = response.json()
            
            if response.status_code == 200 and data.get("status") == "ACCEPTED_ASYNC":
                print(f"   -> OK: Req {i+1} Aceptada y Encolada. ID: {data.get('transaction_id')}")
                queued_transactions += 1
            else:
                print(f"   -> FALLO: Req {i+1} recibió código {response.status_code}. El sistema falló en encolar.")
        except Exception as e:
            print(f"   -> FALLO CRÍTICO: Error de red o timeout: {e}")

    assert queued_transactions == NUM_REQUESTS, f"Fallo: Solo {queued_transactions} de {NUM_REQUESTS} fueron encoladas."

    # 3. Restaurar la Base de Datos
    print(f"\n3. RESTAURANDO SPOF: {DB_CONTAINER_NAME}...")
    run_command(f"docker start {DB_CONTAINER_NAME}")
    
    # 4. CLAVE: Esperar y Verificar la Recuperación (Bucle de reintento)
    print("\n4. ESPERANDO Y VERIFICANDO RECUPERACIÓN (LOGS DEL CONSUMIDOR)...")
    
    processed_count = 0
    for attempt in range(MAX_RECOVERY_ATTEMPTS):
        time.sleep(WAIT_FOR_RECOVERY) # Esperar 5 segundos antes de verificar
        
        # CLAVE: Usamos docker-compose logs para resolver el nombre y buscar el éxito
        logs = run_command(f"docker-compose logs --no-color --since 1m {CONSUMER_SERVICE_NAME}", check_success=False)
        
        # Manejo de caso None si el comando falla totalmente (raro con check=False)
        if logs:
             processed_count = logs.count("CONSUMER SUCCESS: Transacción")
        else:
             processed_count = 0

        print(f"   -> Intento {attempt + 1}: {processed_count} / {queued_transactions} transacciones procesadas.")
        
        if processed_count >= queued_transactions:
            break
        
        if attempt == MAX_RECOVERY_ATTEMPTS - 1:
            assert False, f"Fallo: El consumidor solo procesó {processed_count} de {queued_transactions} transacciones después de {MAX_RECOVERY_ATTEMPTS} intentos."

    print("\n--- TEST E2E DE RESILIENCIA FINALIZADO CON ÉXITO ---")


if __name__ == "__main__":
    test_e2e_resilience()
