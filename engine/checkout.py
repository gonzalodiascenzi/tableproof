"""Link de pago dentro de la conversación.

El flow escribe `{pay_link}` en el mensaje donde va el link de cobro. Este
módulo lo resuelve AL ENVIAR (no al procesar el mensaje entrante): así la
llamada a Mercado Pago queda fuera de la transacción del webhook y, si falla,
el cliente recibe `checkout_failed_message` y el dueño un aviso, en vez de perder
el mensaje en silencio.

- un link por teléfono: si ya hay un pedido pendiente se reutiliza el mismo link;
- si el teléfono ya pagó, el cliente recibe `already_paid_message` (sin segundo pedido);
- salvo con `repeat_purchase: true` en venture.yaml (productos que se recargan, como un paquete
  de consultas): ahí, una vez ENTREGADO el pedido anterior, el mismo teléfono puede comprar otro.
  Un pedido pagado y todavía sin entregar, o con la entrega fallida, sigue bloqueando: primero se
  resuelve ese, para no cobrar dos veces mientras hay un problema abierto;
- el precio sale de la config del dueño (payments.load_venture_config): sin precio no hay pedido.
"""
import secrets

from engine.notify import mask_phone

PAY_TOKEN = "{pay_link}"
SCHEMA = "CREATE TABLE IF NOT EXISTS checkout_links (order_id TEXT PRIMARY KEY, url TEXT NOT NULL)"
BLOCKING = ("pagado", "entregado", "entrega_fallida")
BLOCKING_REPEAT = ("pagado", "entrega_fallida")


class Checkout:
    def __init__(self, orders, client, cfg):
        self.orders, self.client, self.cfg = orders, client, cfg
        self.db = orders.db
        self.db.execute(SCHEMA)
        self.db.commit()

    def link_for(self, phone):
        """-> url del link de pago, o None si este teléfono ya pagó."""
        rows = self.db.execute("SELECT order_id, status FROM orders WHERE phone=? ORDER BY created_at DESC", (phone,)).fetchall()
        blocking = BLOCKING_REPEAT if self.cfg.get("repeat_purchase") is True else BLOCKING
        if any(r[1] in blocking for r in rows):
            return None
        for oid, status in rows:
            if status == "pendiente":
                r = self.db.execute("SELECT url FROM checkout_links WHERE order_id=?", (oid,)).fetchone()
                if r:
                    return r[0]
        order = self.orders.create(phone, secrets.token_hex(8))
        url = self.client.create_preference(order, self.cfg)
        if not url:
            raise RuntimeError("Mercado Pago no devolvió el link de pago")
        self.db.execute("INSERT INTO checkout_links(order_id, url) VALUES (?,?)", (order["order_id"], url))
        self.db.commit()
        return url


class CheckoutSender:
    """Envuelve al sender real: reemplaza `{pay_link}` justo antes de enviar."""

    def __init__(self, inner, checkout, cfg, notify=None):
        self.inner, self.checkout, self.cfg, self.notify = inner, checkout, cfg, notify

    def send_text(self, to, text):
        if PAY_TOKEN in text:
            try:
                link = self.checkout.link_for(to)
            except Exception as e:  # nunca se loguea el cuerpo ni el token
                if self.notify:
                    self.notify(f"no se pudo crear el link de pago para {mask_phone(to)}: {type(e).__name__}")
                return self.inner.send_text(to, self.cfg["checkout_failed_message"])
            text = text.replace(PAY_TOKEN, link) if link else self.cfg["already_paid_message"]
        return self.inner.send_text(to, text)

    def send_template(self, *a, **k):
        return self.inner.send_template(*a, **k)
