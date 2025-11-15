# Diagrama Preliminar de Arquitectura - EventFlow

Este diagrama muestra los componentes principales del sistema EventFlow, destacando la infraestructura de alta disponibilidad (Balanceador, 3 Nodos, Caché, Cola) y el SPOF (BD Única).

```mermaid
graph LR
    subgraph Frontend
        A[Navegador del Usuario/GUI]
    end

    subgraph Infraestructura Central
        LB[Balanceador de Carga NGINX]
        DB[(PostgreSQL BD Única - SPOF)]
        CA[Redis Cache]
        MQ[RabbitMQ/Kafka Cola]
    end

    subgraph Aplicación Principal 3 Nodos
        B1(Nodo 1 - App)
        B2(Nodo 2 - App)
        B3(Nodo 3 - App)
    end

    subgraph Microservicios
        M1(Microservicio 1: Notificaciones)
        M2(Microservicio 2: Análisis)
    end

    A -->|Petición HTTP/S| LB
    LB --> B1
    LB --> B2
    LB --> B3

    B1 -->|Lectura Cache First| CA
    B1 -->|Escritura Asíncrona| MQ
    B1 -->|Lectura Directa Fallback| DB
    B1 -->|Consulta API REST| M2

    MQ -->|Consumidor de Escrituras| DB
    MQ -->|Eventos de Notificación| M1

    M2 -->|Lectura de Datos Históricos| DB

    style DB fill:#f99,stroke:#333,stroke-width:2px
    style CA fill:#ccf,stroke:#333,stroke-width:2px
    style MQ fill:#ccf,stroke:#333,stroke-width:2px
    style LB fill:#aaf,stroke:#333,stroke-width:2px
    style B1 fill:#afa,stroke:#333,stroke-width:2px
    style B2 fill:#afa,stroke:#333,stroke-width:2px
    style B3 fill:#afa,stroke:#333,stroke-width:2px
