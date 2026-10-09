"""Estado de cada conversación en sqlite. Nada de datos sensibles: solo teléfono
(identificador del canal), estado, fechas y el texto de los eventos (el entrante se trunca y se enmascaran números largos)."""
import re
import sqlite3
from contextlib import contextmanager

MAX_TEXT = 200
_LONG_NUM = re.compile(r"\d[\d\s\-\.]{4,}\d")


def sanitize_inbound(text):
    """Lo que el cliente escribe puede traer datos sensibles (CBU, DNI, tarjeta): se
    enmascaran las secuencias numéricas largas y se trunca antes de guardar."""
    if text is None:
        return None
    return _LONG_NUM.sub("[num]", text)[:MAX_TEXT]

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
    def __init__(self, path=":memory:", threadsafe=False):
        # threadsafe: la conexión se comparte entre hilos; quien la use debe serializar (ver WebhookHandler)
        self.db = sqlite3.connect(path, check_same_thread=not threadsafe)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._tx = 0

    def _commit(self):
        if not self._tx:
            self.db.commit()

    @contextmanager
    def transaction(self):
        """Todo lo escrito adentro se confirma junto o no se confirma (rollback si falla)."""
        self._tx += 1
        try:
            yield
        except BaseException:
            self._tx -= 1
            if not self._tx:
                self.db.rollback()
            raise
        self._tx -= 1
        if not self._tx:
            self.db.commit()

    def contact(self, phone):
        r = self.db.execute("SELECT * FROM contacts WHERE phone=?", (phone,)).fetchone()
        return dict(r) if r else None

    def ensure(self, phone):
        self.db.execute("INSERT OR IGNORE INTO contacts(phone) VALUES (?)", (phone,))
        self._commit()
        return self.contact(phone)

    def update(self, phone, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE contacts SET {cols} WHERE phone=?", (*fields.values(), phone))
        self._commit()

    def log(self, phone, ts, direction, text, note=None):
        if direction == "in":
            text = sanitize_inbound(text)
        self.db.execute("INSERT INTO events(phone, ts, direction, text, note) VALUES (?,?,?,?,?)",
                        (phone, ts, direction, text, note))
        self._commit()

    def events(self, phone):
        return [dict(r) for r in self.db.execute("SELECT * FROM events WHERE phone=? ORDER BY id", (phone,))]

    def close(self):
        self.db.close()
