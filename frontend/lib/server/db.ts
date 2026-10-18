import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { DatabaseSync } from 'node:sqlite'

const SCHEMA_VERSION = 1

const SCHEMA = `
  CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    INTEGER NOT NULL
  );
  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
`

const FROM_V0 = `
  PRAGMA foreign_keys = OFF;
  BEGIN;
  DROP TABLE IF EXISTS otp_challenges;
  CREATE TABLE users_v1 (
    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL
  );
  INSERT INTO users_v1 (id, email, password_hash, created_at) SELECT id, lower(email), password_hash, created_at FROM users;
  DROP TABLE users;
  ALTER TABLE users_v1 RENAME TO users;
  COMMIT;
  PRAGMA foreign_keys = ON;
`

function migrate(conn: DatabaseSync) {
  const { user_version: version } = conn.prepare('PRAGMA user_version').get() as { user_version: number }
  if (version >= SCHEMA_VERSION) return
  const hasUsers = conn.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").get()
  if (hasUsers) conn.exec(FROM_V0)
  conn.exec(SCHEMA)
  conn.exec(`PRAGMA user_version = ${SCHEMA_VERSION}`)
}

const g = globalThis as unknown as { __rhizoAuthDb?: { path: string; conn: DatabaseSync } }

export function db(): DatabaseSync {
  const path = resolve(/* turbopackIgnore: true */ process.env.AUTH_DB_PATH ?? '.data/auth.db')
  if (g.__rhizoAuthDb?.path !== path) {
    mkdirSync(dirname(path), { recursive: true })
    const conn = new DatabaseSync(path)
    conn.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;')
    migrate(conn)
    g.__rhizoAuthDb = { path, conn }
  }
  return g.__rhizoAuthDb.conn
}
