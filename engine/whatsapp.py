"""Conexión con la WhatsApp Cloud API (webhook + envío). Sin dependencias nuevas.

Lo que sale de la documentación oficial de Meta (leída el 2026-10-08, ver
docs/meta-verificado.md):
- GET de verificación: hub.mode (siempre "subscribe"), hub.verify_token,
  hub.challenge (hay que devolverlo).
- POST: cabecera X-Hub-Signature-256 = "sha256=" + HMAC-SHA256 del payload con
  el App Secret.
- Payload entrante: entry[].changes[].value.messages[] con from, id,
  timestamp, type, text.body.
- Envío: POST https://graph.facebook.com/{versión}/{phone_number_id}/messages
  con Authorization: Bearer, messaging_product, to, type, text.body o
  template.name + template.language.code.

[hipótesis] la firma se calcula sobre los BYTES CRUDOS del cuerpo (la página
dice "the payload" sin precisar): se prueba con un payload real de Meta.
La versión de la API NO está escrita acá: viene de WHATSAPP_API_VERSION.
Los secretos viven solo en variables de entorno; nunca se loguean.
"""
import hashlib
import hmac
import json
import os
import urllib.request
from dataclasses import dataclass

ENV_REQUIRED = ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_ACCESS_TOKEN",
                "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_API_VERSION")


def missing_env(env=None):
    env = os.environ if env is None else env
    return [k for k in ENV_REQUIRED if not env.get(k)]


# ---- verificación -------------------------------------------------------
def verify_challenge(params, verify_token):
    """params: dict de query (valores de texto). -> (status, body)."""
    if params.get("hub.mode") != "subscribe":
        return 403, "modo inválido"
    token = params.get("hub.verify_token") or ""
    if not verify_token or not hmac.compare_digest(token.encode(), verify_token.encode()):
        return 403, "token inválido"
    challenge = params.get("hub.challenge")
    if challenge is None:
        return 400, "falta hub.challenge"
    return 200, challenge


def verify_signature(raw_body, header, app_secret):
    """True solo si 'sha256=<hmac>' coincide con el HMAC-SHA256 del cuerpo crudo."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256="):].strip().lower(), expected)


def sign(raw_body, app_secret):
    """Para pruebas locales: arma la cabecera que mandaría Meta."""
    return "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()


# ---- payload entrante ---------------------------------------------------
@dataclass
class Inbound:
    msg_id: str
    sender: str
    timestamp: float
    type: str
    text: str


def parse_inbound(payload):
    """Extrae los mensajes entrantes. Ignora estados y lo que no sea un mensaje."""
    out = []
    for entry in payload.get("entry") or []:
        for ch in entry.get("changes") or []:
            if ch.get("field") != "messages":
                continue
            for m in (ch.get("value") or {}).get("messages") or []:
                if not m.get("id") or not m.get("from"):
                    continue
                try:
                    ts = float(m.get("timestamp"))
                except (TypeError, ValueError):
                    continue
                typ = m.get("type") or "unknown"
                text = (m.get("text") or {}).get("body", "") if typ == "text" else ""
                out.append(Inbound(m["id"], m["from"], ts, typ, text))
    return out


# ---- envío --------------------------------------------------------------
class CloudApiSender:
    """Envía por la Cloud API. El token se lee del entorno y no aparece en repr ni en logs."""

    def __init__(self, phone_number_id, token, api_version, post=None):
        if not (phone_number_id and token and api_version):
            raise ValueError("faltan phone_number_id, token o api_version")
        self._phone_number_id, self._token, self._version = phone_number_id, token, api_version
        self._post = post or self._http_post

    @classmethod
    def from_env(cls, env=None, post=None):
        env = os.environ if env is None else env
        miss = missing_env(env)
        if miss:
            raise ValueError("faltan variables de entorno: " + ", ".join(miss))
        return cls(env["WHATSAPP_PHONE_NUMBER_ID"], env["WHATSAPP_ACCESS_TOKEN"], env["WHATSAPP_API_VERSION"], post)

    def __repr__(self):
        return f"CloudApiSender(phone_number_id={self._phone_number_id!r}, version={self._version!r})"

    def _request(self, body):
        url = f"https://graph.facebook.com/{self._version}/{self._phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        return url, headers, body

    def send_text(self, to, text):
        body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
        return self._post(*self._request(body))

    def send_template(self, to, name, language_code):
        body = {"messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {"name": name, "language": {"code": language_code}}}
        return self._post(*self._request(body))

    @staticmethod
    def _http_post(url, headers, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
