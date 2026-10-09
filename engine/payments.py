"""Cobro con Mercado Pago (modo de prueba) y entrega automática.

Reglas que hace cumplir el código:
- la entrega se activa SOLO desde `PaymentHandler`, tras una notificación con
  firma válida Y la confirmación del pago consultando la API de Mercado Pago
  (GET /v1/payments/{id}). Ningún mensaje del cliente ni captura llega a la
  entrega: el respondedor (engine/responder.py) no importa este módulo.
- el precio sale de la configuración del emprendimiento; sin precio no se
  crea ningún pedido. No hay precio por defecto.
- solo modo de prueba: el cliente exige MP_MODE=test y rechaza notificaciones
  con live_mode verdadero. Las credenciales salen de variables de entorno.
- cada evento de pago y de entrega queda en sqlite.

[hipótesis] (la documentación leída no lo especificaba; ver docs/mercadopago-verificado.md):
- el manifiesto de la firma: `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`
  firmado con HMAC-SHA256 (hex) con la clave secreta, comparado con `v1`;
- el valor de `status` que significa pago aprobado: "approved";
- el endpoint y los campos para crear la preferencia de pago.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.request

API = "https://api.mercadopago.com"
APPROVED = "approved"  # [hipótesis]
ENV_REQUIRED = ("MP_ACCESS_TOKEN", "MP_WEBHOOK_SECRET", "MP_MODE")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, phone TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL,
  status TEXT NOT NULL, mp_payment_id TEXT, created_at REAL, paid_at REAL, delivered_at REAL,
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT
);
CREATE TABLE IF NOT EXISTS payment_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, order_id TEXT, mp_payment_id TEXT, kind TEXT, note TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_approval ON payment_events(mp_payment_id) WHERE kind='aprobado';
CREATE TABLE IF NOT EXISTS delivery_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, order_id TEXT, attempt INTEGER, ok INTEGER, note TEXT
);
"""


class ConfigError(ValueError):
    pass


def load_venture_config(cfg):
    """Valida la config de cobro de un emprendimiento. Nada tiene valor por defecto salvo reintentos."""
    price = cfg.get("price_ars")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise ConfigError("price_ars: lo define el dueño; no hay precio por defecto")
    for k in ("item_title", "notification_url", "delivery_failed_message"):
        if not str(cfg.get(k) or "").strip():
            raise ConfigError(f"falta '{k}' en la config del emprendimiento")
    if not str(cfg["notification_url"]).startswith("https://"):
        raise ConfigError("notification_url debe ser https")
    out = dict(cfg)
    out.setdefault("currency", "ARS")
    out.setdefault("delivery_max_attempts", 3)
    return out


# ---- firma ---------------------------------------------------------------
def parse_signature(header):
    parts = {}
    for p in (header or "").split(","):
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k.strip()] = v.strip()
    return parts.get("ts"), parts.get("v1")


def mp_sign(secret, data_id, request_id, ts):
    """Para pruebas locales: arma la cabecera x-signature que mandaría Mercado Pago [hipótesis de formato]."""
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    return f"ts={ts},v1=" + hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()


def verify_mp_signature(secret, x_signature, x_request_id, data_id):
    ts, v1 = parse_signature(x_signature)
    if not (secret and ts and v1):
        return False
    # [verificado 2026-10-08, doc de Mercado Pago, leída con resumidor]: plantilla
    # "id:{data.id};request-id:{x-request-id};ts:{ts};" y se omite el par cuyo valor no viene.
    did = data_id.lower() if data_id and data_id.isalnum() else data_id  # minúsculas: [hipótesis] (lo hacen los SDK de ejemplo, la prosa no lo dice)
    parts = []
    if did:
        parts.append(f"id:{did};")
    if x_request_id:
        parts.append(f"request-id:{x_request_id};")
    parts.append(f"ts:{ts};")
    manifest = "".join(parts)
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(v1.lower(), expected)


# ---- cliente de la API ---------------------------------------------------
class MercadoPagoClient:
    """Solo modo de prueba. El token no aparece en repr ni en logs."""

    def __init__(self, access_token, mode, request=None):
        if mode != "test":
            raise ConfigError("MP_MODE debe ser 'test': este motor no opera en producción")
        if not access_token:
            raise ConfigError("falta MP_ACCESS_TOKEN (credencial de PRUEBA)")
        self._token, self._request = access_token, request or self._http

    @classmethod
    def from_env(cls, env=None, request=None):
        env = os.environ if env is None else env
        miss = [k for k in ("MP_ACCESS_TOKEN", "MP_MODE") if not env.get(k)]
        if miss:
            raise ConfigError("faltan variables de entorno: " + ", ".join(miss))
        return cls(env["MP_ACCESS_TOKEN"], env["MP_MODE"], request)

    def __repr__(self):
        return "MercadoPagoClient(mode='test')"

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def get_payment(self, payment_id):
        return self._request("GET", f"{API}/v1/payments/{payment_id}", self._headers(), None)

    def create_preference(self, order, cfg):
        """[hipótesis] endpoint y campos de la preferencia (una por pedido). Devuelve el link de pago."""
        body = {"items": [{"title": cfg["item_title"], "quantity": 1, "unit_price": order["amount"],
                           "currency_id": order["currency"]}],
                "external_reference": order["order_id"], "notification_url": cfg["notification_url"]}
        resp = self._request("POST", f"{API}/checkout/preferences", self._headers(), body)
        return resp.get("init_point")

    @staticmethod
    def _http(method, url, headers, body):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())


# ---- pedidos -------------------------------------------------------------
class Orders:
    def __init__(self, store, cfg, clock=time.time, notifier=None):
        self.db, self.cfg, self.clock = store.db, cfg, clock
        self._notifier = notifier
        self.db.executescript(SCHEMA)
        self.db.row_factory = store.db.row_factory

    def create(self, phone, order_id):
        now = self.clock()
        self.db.execute("INSERT INTO orders(order_id, phone, amount, currency, status, created_at) VALUES (?,?,?,?,?,?)",
                        (order_id, phone, self.cfg["price_ars"], self.cfg["currency"], "pendiente", now))
        self.db.commit()
        return self.get(order_id)

    def notify(self, msg):
        """Avisa al dueño. Sin canal configurado queda registrado igual (no se pierde en silencio)."""
        n = self._notifier or self.cfg.get("_notifier")
        if not n:
            self.log_delivery(None, 0, False, "aviso_sin_canal")
            return
        try:
            n(msg)
        except Exception as e:
            self.log_delivery(None, 0, False, "aviso_fallido:" + type(e).__name__)

    def get(self, order_id):
        r = self.db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return dict(r) if r else None

    def update(self, order_id, **f):
        cols = ", ".join(f"{k}=?" for k in f)
        self.db.execute(f"UPDATE orders SET {cols} WHERE order_id=?", (*f.values(), order_id))
        self.db.commit()

    def log_payment(self, order_id, payment_id, kind, note=None):
        try:
            self.db.execute("INSERT INTO payment_events(ts, order_id, mp_payment_id, kind, note) VALUES (?,?,?,?,?)",
                            (self.clock(), order_id, payment_id, kind, note))
            self.db.commit()
            return True
        except Exception:  # índice único: ese pago ya fue aprobado antes
            return False

    def log_delivery(self, order_id, attempt, ok, note=None):
        self.db.execute("INSERT INTO delivery_events(ts, order_id, attempt, ok, note) VALUES (?,?,?,?,?)",
                        (self.clock(), order_id, attempt, 1 if ok else 0, note))
        self.db.commit()

    def events(self, table):
        return [dict(r) for r in self.db.execute(f"SELECT * FROM {table} ORDER BY id")]


# ---- entrega -------------------------------------------------------------
def deliver_with_retries(orders, order_id, deliverer, sender, store, sleep=time.sleep, backoff=1.0):
    """Entrega una sola vez. Reintenta; si sigue fallando, avisa al dueño y le dice al cliente cómo hablar con una persona."""
    cfg = orders.cfg
    for attempt in range(1, int(cfg["delivery_max_attempts"]) + 1):
        o = orders.get(order_id)
        if o["status"] == "entregado":
            return True
        try:
            deliverer.deliver(o)
        except Exception as e:  # nunca se registra el contenido, solo el tipo de error
            orders.update(order_id, attempts=attempt, last_error=type(e).__name__)
            orders.log_delivery(order_id, attempt, False, type(e).__name__)
            if attempt < int(cfg["delivery_max_attempts"]):
                sleep(backoff * attempt)
            continue
        orders.update(order_id, status="entregado", delivered_at=orders.clock(), attempts=attempt, last_error=None)
        orders.log_delivery(order_id, attempt, True)
        return True
    orders.update(order_id, status="entrega_fallida")
    store.update(o["phone"], human=1)  # el bot deja de responder: lo toma una persona
    try:
        sender.send_text(o["phone"], cfg["delivery_failed_message"])
    except Exception as e:
        orders.log_delivery(order_id, 0, False, "aviso_cliente_fallido:" + type(e).__name__)
    orders.notify(f"entrega fallida del pedido {order_id}")
    return False


class PaymentHandler:
    def __init__(self, orders, client, deliverer, sender, store, webhook_secret, sleep=time.sleep, backoff=1.0):
        self.orders, self.client, self.deliverer, self.sender, self.store = orders, client, deliverer, sender, store
        self.secret, self.sleep, self.backoff = webhook_secret, sleep, backoff

    def handle(self, query, headers, raw_body):
        """query: dict de query (data.id); headers: dict con x-signature y x-request-id. -> (status, texto)"""
        h = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, "json inválido"
        if not isinstance(body, dict):
            return 400, "payload inválido"
        data_id = str(query.get("data.id") or (body.get("data") or {}).get("id") or "")
        if not verify_mp_signature(self.secret, h.get("x-signature"), h.get("x-request-id"), data_id):
            self.orders.log_payment(None, data_id or None, "firma_invalida")
            return 401, "firma inválida"
        if body.get("type") != "payment":
            return 200, "ignorado (no es de pagos)"
        if body.get("live_mode") is True:
            self.orders.log_payment(None, data_id, "rechazado", "live_mode en modo de prueba")
            return 200, "ignorado (live_mode)"
        try:
            pay = self.client.get_payment(data_id)  # la autenticidad real: lo dice la API, no el mensaje
        except Exception as e:
            self.orders.log_payment(None, data_id, "consulta_fallida", type(e).__name__)
            return 500, "no se pudo consultar el pago"  # Mercado Pago reintenta
        order = self.orders.get(str(pay.get("external_reference") or ""))
        if not order:
            self.orders.log_payment(None, data_id, "rechazado", "pedido desconocido")
            return 200, "pedido desconocido"
        if pay.get("status") != APPROVED:
            self.orders.log_payment(order["order_id"], data_id, "estado:" + str(pay.get("status")))
            return 200, "pago no aprobado"
        if float(pay.get("transaction_amount") or 0) != float(order["amount"]) or pay.get("currency_id") != order["currency"]:
            self.orders.log_payment(order["order_id"], data_id, "rechazado", "monto o moneda no coinciden")
            return 200, "monto no coincide"
        if not self.orders.log_payment(order["order_id"], data_id, "aprobado"):
            return 200, "ya procesado"  # notificación duplicada o replay
        if order["status"] == "pendiente":
            self.orders.update(order["order_id"], status="pagado", mp_payment_id=data_id, paid_at=self.orders.clock())
            deliver_with_retries(self.orders, order["order_id"], self.deliverer, self.sender, self.store, self.sleep, self.backoff)
        return 200, "ok"
