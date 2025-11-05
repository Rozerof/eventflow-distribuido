EventFlow — Sistema Distribuido Resiliente
-----
Proyecto Final — Sistemas Distribuidos
-------
EventFlow es una plataforma de venta y gestión de tickets diseñada con arquitectura de microservicios, enfocada en Alta Disponibilidad y Tolerancia a Fallos.

Objetivo: demostrar que el sistema continúa aceptando y procesando transacciones (escrituras) y atendiendo consultas (lecturas) aun cuando la Base de Datos Principal (SPOF) se encuentra caída.
------
Arquitectura del Sistema

El sistema implementa un patrón de mensajería asíncrona y caché para evitar dependencia directa de la base de datos principal.

Componente	Rol en la Resiliencia	Tecnología
Backend Principal	Distribución de tráfico y lógica resiliente	FastAPI (3 nodos)
Balanceador	Distribución y health check	NGINX
SPOF — Base de Datos Principal	Punto de fallo controlado	PostgreSQL
Caché	Lecturas rápidas y soporte en caída	Redis
Cola de Mensajes	Persistencia de escrituras durante caída	RabbitMQ
Microservicio Notificaciones	Procesamiento diferido y reintentos	Python Script
Microservicio Análisis	API para consultas analíticas	FastAPI
Monitoreo	Métricas y paneles	Prometheus + Grafana
Requisitos Previos
-------
Instalar antes de ejecutar:

Docker Desktop (con backend WSL2/Linux)

Docker Compose

Python 3+

Librerías Python necesarias:

pip install requests

Despliegue del Sistema

Desde la carpeta raíz del proyecto:
-------
Arranque
docker-compose up --build -d


Esto iniciará los contenedores de microservicios, PostgreSQL, Redis, RabbitMQ, NGINX, Prometheus y Grafana.
--------
Endpoints Principales
Servicio	URL	Descripción
GUI Web	http://localhost/
	Interfaz principal
Balanceador (Health Check)	http://localhost/health
	Estado de nodos
RabbitMQ Dashboard	http://localhost:15672
	Gestión de cola (guest/guest)
Prometheus	http://localhost:9090
	Métricas
Grafana	http://localhost:3000
	Dashboards (admin/admin)
Prueba de Tolerancia a Fallos (E2E)

Este test demuestra la capacidad de realizar compras mientras la base de datos está caída.

Ejecución del Test
python eventflow-distribuido/tests/e2e_resilience_test.py

Condiciones de éxito

Detener el contenedor postgres_spof

Enviar 5 peticiones POST a /purchase

Recibir respuesta ACCEPTED_ASYNC

Reactivar la base de datos

Confirmar que el consumidor procese las 5 transacciones

Mensaje esperado:
---------
--- TEST E2E DE RESILIENCIA FINALIZADO CON ÉXITO ---

Pruebas Unitarias e Integración
Módulo	Tests	Cobertura
App Principal	3	Validaciones y cálculo de precios
Notificaciones	2	Estructura de mensaje y lectura de cola
Análisis	2	Ingresos y manejo de datos nulos
Funciones comunes	2	Hashing y verificación Redis
E2E Resiliencia	1	Compra con fallo de base de datos

Total pruebas: 10

Video de Evidencia

La demostración incluye:

Compra y consulta con base de datos operativa

Detención de PostgreSQL

5 compras procesadas de forma asíncrona

Visualización en Grafana de caída del servicio

Reactivación de BD y procesamiento en cola

Realizado por

María Medina
Laura Malagón
