"""Entrega automática tras un pago confirmado: acceso (clave de licencia) o descarga.

Se engancha como `deliverer` de `engine.payments.PaymentHandler`: solo corre
cuando el pago ya fue confirmado por la API de Mercado Pago (ver payments.py).
Es idempotente: reintentar una entrega no duplica la clave ni el mensaje.

- kind `access`: se emite una clave por pedido (`TP-XXXX-XXXX-XXXX`, 64 bits al
  azar) y se manda por whatsapp con la URL de acceso. Quien tenga el producto
  puede validar una clave con `GET /verify?key=...` (ver engine/app.py).
- kind `download`: se manda un link firmado (HMAC-SHA256) que vence y que tiene un
  tope de descargas. El archivo vive en `ventures/<slug>/entrega/` y está
  excluido de git. Los valores técnicos por defecto (72 h, 5 descargas) no son
  decisiones de negocio; se cambian en venture.yaml.

Límites conocidos:
- [hipótesis] el mensaje de entrega es un texto libre: si el cliente paga pasadas
  24 h desde su último mensaje, whatsapp puede rechazarlo; la entrega falla,
  se reintenta y queda `entrega_fallida` con aviso al dueño (ver payments.py).
- la clave se valida por búsqueda exacta, sin límite de intentos: con 64 bits al
  azar no se adivina a mano, pero poné un límite de tasa adelante si exponés /verify.
- reembolsos y contracargos no revocan nada solos (avisan al dueño):
  `python -m engine.delivery revoke <db> <clave>`.
"""
import base64
import hashlib
import hmac
import secrets
import sys
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
  order_id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, created_at REAL, sent_at REAL, revoked_at REAL
);
CREATE TABLE IF NOT EXISTS download_counts (order_id TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
"""
PAID = ("pagado", "entregado")
DEFAULT_TTL_HOURS = 72
DEFAULT_MAX_DOWNLOADS = 5


def new_key():
    raw = secrets.token_hex(8).upper()
    return "TP-" + "-".join(raw[i:i + 4] for i in range(0, 16, 4))


class Licenses:
    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock
        self.db.executescript(SCHEMA)

    def issue(self, order_id):
        """Una clave por pedido; pedirla de nuevo devuelve la misma."""
        self.db.execute("INSERT OR IGNORE INTO licenses(order_id, key, created_at) VALUES (?,?,?)",
                        (order_id, new_key(), self.clock()))
        self.db.commit()
        return self.db.execute("SELECT key FROM licenses WHERE order_id=?", (order_id,)).fetchone()[0]

    def sent(self, order_id):
        r = self.db.execute("SELECT sent_at FROM licenses WHERE order_id=?", (order_id,)).fetchone()
        return bool(r and r[0] is not None)

    def mark_sent(self, order_id):
        self.db.execute("UPDATE licenses SET sent_at=? WHERE order_id=?", (self.clock(), order_id))
        self.db.commit()

    def verify(self, key):
        """True si la clave existe, no fue revocada y su pedido está pagado."""
        r = self.db.execute("SELECT l.revoked_at, o.status FROM licenses l JOIN orders o ON o.order_id=l.order_id WHERE l.key=?",
                            (str(key or ""),)).fetchone()
        return bool(r and r[0] is None and r[1] in PAID)

    def revoke(self, key):
        cur = self.db.execute("UPDATE licenses SET revoked_at=? WHERE key=? AND revoked_at IS NULL", (self.clock(), key))
        self.db.commit()
        return cur.rowcount == 1


# ---- links de descarga firmados -----------------------------------------
def make_token(secret, order_id, exp):
    payload = base64.urlsafe_b64encode(f"{order_id}|{int(exp)}".encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_token(secret, token, now):
    """-> order_id si la firma es válida y no venció; si no, None."""
    try:
        payload, sig = str(token).split(".", 1)
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig.lower(), expected):
            return None
        order_id, exp = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rsplit("|", 1)
        return order_id if now <= float(exp) else None
    except (ValueError, UnicodeDecodeError):
        return None


class DownloadService:
    def __init__(self, db, secret, file_path, base_url, ttl_hours=DEFAULT_TTL_HOURS, max_downloads=DEFAULT_MAX_DOWNLOADS, clock=time.time):
        if not secret:
            raise ValueError("falta DELIVERY_SECRET (inventá una cadena larga al azar)")
        self.db, self.secret, self.file_path = db, secret, file_path
        self.base_url, self.ttl, self.max, self.clock = base_url.rstrip("/"), ttl_hours * 3600, int(max_downloads), clock
        self.db.executescript(SCHEMA)

    def url_for(self, order_id):
        return f"{self.base_url}/d/{make_token(self.secret, order_id, self.clock() + self.ttl)}"

    def authorize(self, token):
        """-> (status_http, order_id|None). Cuenta la descarga al autorizar."""
        oid = parse_token(self.secret, token, self.clock())
        if not oid:
            return 403, None
        o = self.db.execute("SELECT status FROM orders WHERE order_id=?", (oid,)).fetchone()
        if not o or o[0] not in PAID:
            return 403, None
        self.db.execute("INSERT OR IGNORE INTO download_counts(order_id, n) VALUES (?,0)", (oid,))
        cur = self.db.execute("UPDATE download_counts SET n=n+1 WHERE order_id=? AND n<?", (oid, self.max))
        self.db.commit()
        return (200, oid) if cur.rowcount == 1 else (403, None)


# ---- entregadores (los usa PaymentHandler) ------------------------------
class AccessDeliverer:
    def __init__(self, licenses, sender, cfg):
        self.licenses, self.sender, self.cfg = licenses, sender, cfg

    def deliver(self, order):
        oid = order["order_id"]
        if self.licenses.sent(oid):
            return
        key = self.licenses.issue(oid)
        self.sender.send_text(order["phone"], self.cfg["delivery_message"].format(key=key, url=self.cfg["access_url"]))
        self.licenses.mark_sent(oid)


class DownloadDeliverer:
    def __init__(self, licenses, downloads, sender, cfg):
        self.licenses, self.downloads, self.sender, self.cfg = licenses, downloads, sender, cfg

    def deliver(self, order):
        oid = order["order_id"]
        if self.licenses.sent(oid):
            return
        self.licenses.issue(oid)
        self.sender.send_text(order["phone"], self.cfg["delivery_message"].format(url=self.downloads.url_for(oid)))
        self.licenses.mark_sent(oid)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 3 and argv[0] == "revoke":
        import sqlite3
        db = sqlite3.connect(argv[1])
        ok = Licenses(db).revoke(argv[2])
        print("revocada" if ok else "no encontrada o ya revocada")
        return 0 if ok else 1
    print("uso: python -m engine.delivery revoke <archivo.sqlite> <clave>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
