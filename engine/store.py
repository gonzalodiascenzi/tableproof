"""Estado de cada conversación en sqlite. Nada de datos sensibles: solo teléfono
(identificador del canal), estado, fechas y el texto de los eventos."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
  phone TEXT PRIMARY KEY,
  state TEXT,
  opt_in_at REAL, opt_in_source TEXT,
  opt_out_at REAL,
  last_user_at REAL,
  human INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL, ts REAL NOT NULL, direction TEXT NOT NULL, text TEXT, note TEXT
);
"""


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def contact(self, phone):
        r = self.db.execute("SELECT * FROM contacts WHERE phone=?", (phone,)).fetchone()
        return dict(r) if r else None

    def ensure(self, phone):
        self.db.execute("INSERT OR IGNORE INTO contacts(phone) VALUES (?)", (phone,))
        self.db.commit()
        return self.contact(phone)

    def update(self, phone, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE contacts SET {cols} WHERE phone=?", (*fields.values(), phone))
        self.db.commit()

    def log(self, phone, ts, direction, text, note=None):
        self.db.execute("INSERT INTO events(phone, ts, direction, text, note) VALUES (?,?,?,?,?)",
                        (phone, ts, direction, text, note))
        self.db.commit()

    def events(self, phone):
        return [dict(r) for r in self.db.execute("SELECT * FROM events WHERE phone=? ORDER BY id", (phone,))]

    def close(self):
        self.db.close()
