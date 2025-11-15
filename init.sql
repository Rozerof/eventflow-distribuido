-- Este script se ejecuta automáticamente cuando el contenedor de PostgreSQL se inicia por primera vez.

-- Tabla para usuarios del sistema de autenticación
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para los eventos
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    date TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Tabla para las compras de tickets
CREATE TABLE IF NOT EXISTS purchases (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- Insertar datos de ejemplo para eventos (Insertar solo si ID no existe)
INSERT INTO events (id, name, description, date) 
SELECT 999, 'Concierto de Resiliencia', 'Un evento para probar la arquitectura Cache-Aside.', '2025-12-01T20:00:00Z'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE id = 999);

-- Insertar datos de ejemplo para usuarios (Insertar solo si ID no existe)
INSERT INTO users (id, username, email, hashed_password) 
SELECT 1, 'testuser', 'test@example.com', '$2b$12$EixZaYVK1fsbw/WBZ3J9A.T6m2w.g2b.j2X.Yg2b.j2X.Yg2b.j2'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 1);