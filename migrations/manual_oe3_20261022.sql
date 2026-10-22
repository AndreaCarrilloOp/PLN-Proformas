-- Ejecutar una sola vez en copia de seguridad de PostgreSQL ANTES de desplegar el nuevo código.
-- Revisar las solicitudes históricas sin dueño: no asignarlas a otro usuario automáticamente.
BEGIN;
ALTER TABLE usuario_local ADD COLUMN IF NOT EXISTS role VARCHAR(24) NOT NULL DEFAULT 'USUARIO_FINAL';
ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS owner_user_id INTEGER;
ALTER TABLE articulo_solicitud ADD COLUMN IF NOT EXISTS unit_measure_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_solicitud_owner_user_id ON solicitud (owner_user_id);
DO $$ BEGIN
  ALTER TABLE solicitud ADD CONSTRAINT fk_solicitud_owner FOREIGN KEY(owner_user_id) REFERENCES usuario_local(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE articulo_solicitud ADD CONSTRAINT fk_articulo_unidad FOREIGN KEY(unit_measure_id) REFERENCES unidad_medida(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS smtp_cuenta_usuario (
 user_id INTEGER PRIMARY KEY REFERENCES usuario_local(id),
 host VARCHAR(200) NOT NULL,
 port INTEGER NOT NULL DEFAULT 587,
 username VARCHAR(200),
 from_email VARCHAR(200) NOT NULL,
 password_encrypted TEXT,
 use_tls BOOLEAN NOT NULL DEFAULT TRUE
);
COMMIT;
-- No ejecutar un UPDATE general de roles ni propietarios. Asignarlos con control humano.
-- Comprobar antes y después: SELECT COUNT(*) FROM solicitud WHERE owner_user_id IS NULL;
