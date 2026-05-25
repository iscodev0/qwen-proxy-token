import { Database } from "bun:sqlite";
import { join } from "path";

const DB_PATH = join(import.meta.dir, "../../hubia.db");

let db: Database | null = null;

export function getDb(): Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.exec("PRAGMA journal_mode = WAL");
    db.exec("PRAGMA foreign_keys = ON");
    initDb();
  }
  return db;
}

function initDb() {
  const database = getDb();

  database.exec(`
    CREATE TABLE IF NOT EXISTS credentials (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL DEFAULT 1,
      provider TEXT NOT NULL,
      encrypted_cookies TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')),
      expires_at TEXT,
      UNIQUE(user_id, provider)
    )
  `);

  database.exec(`
    CREATE INDEX IF NOT EXISTS idx_credentials_user_provider 
    ON credentials(user_id, provider)
  `);
}

export function closeDb() {
  if (db) {
    db.close();
    db = null;
  }
}
