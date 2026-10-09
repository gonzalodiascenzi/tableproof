"""Handler del webhook: firma, idempotencia y entrega al respondedor.

- Firma inválida -> 403 y NO se procesa nada.
- Idempotencia: cada message id se procesa una sola vez (tabla processed), en la misma transacción que el avance de estado (falla -> rollback + 500 -> Meta reintenta). Meta
  reintenta hasta 7 días, así que los ids procesados NO se purgan antes de 8 días.
- No hay tolerancia de timestamp a propósito: un reintento legítimo puede llegar
  días después. Un replay de un payload firmado se frena por el message id.
- Si el envío falla, se registra el evento 'envio_fallido' (sin cuerpo ni token) y se responde 200:
  el estado ya avanzó y un reintento de Meta lo duplicaría.
- Responde 200 rápido a lo que no es un mensaje (estados, tipos no soportados)
  para que Meta no reintente.
"""
import json
import threading

from engine import whatsapp as wa


class WebhookHandler:
    def __init__(self, responder, sender, app_secret, verify_token, language_code="es"):
        self.r, self.sender = responder, sender
        self.app_secret, self.verify_token, self.lang = app_secret, verify_token, language_code
        self._lock = threading.Lock()  # una conexión sqlite compartida: se serializa el procesamiento
        self.r.store.db.execute("CREATE TABLE IF NOT EXISTS processed (msg_id TEXT PRIMARY KEY, ts REAL)")
        self.r.store.db.commit()

    def handle_get(self, params):
        return wa.verify_challenge(params, self.verify_token)

    def handle_post(self, raw_body, signature_header):
        if not wa.verify_signature(raw_body, signature_header, self.app_secret):
            return 403, "firma inválida"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, "json inválido"
        if not isinstance(payload, dict):
            return 400, "payload inválido"
        with self._lock:
            return self._process(payload)

    def _process(self, payload):
        handled = 0
        for m in wa.parse_inbound(payload):
            # "procesado" y el avance de estado se confirman juntos: si algo falla,
            # rollback y 500 -> Meta reintenta y el mensaje no se pierde.
            try:
                with self.r.store.transaction():
                    cur = self.r.store.db.execute("INSERT OR IGNORE INTO processed(msg_id, ts) VALUES (?,?)", (m.msg_id, m.timestamp))
                    if cur.rowcount == 0:
                        continue  # ya procesado (reintento o replay)
                    replies = self.r.handle_incoming(m.sender, m.text, ts=m.timestamp)
            except Exception:
                return 500, "error al procesar; reintentá"
            for reply in replies:
                try:
                    self.sender.send_text(m.sender, reply)
                except Exception as e:  # el estado ya avanzó: no se pide reintento (duplicaría el avance)
                    self.r.store.log(m.sender, m.timestamp, "envio_fallido", None, type(e).__name__)
            handled += 1
        return 200, f"ok ({handled} procesado(s))"
