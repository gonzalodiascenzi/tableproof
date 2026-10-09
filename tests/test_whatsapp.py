import json
import unittest

from engine import whatsapp as wa
from engine.devtools import example_payload
from engine.responder import Clock, Responder
from engine.store import Store
from engine.webhook import WebhookHandler
from engine.flow import load_flow
from tests.test_engine import FIX

SECRET = "SECRETO_DE_PRUEBA_NO_REAL"
VERIFY = "TOKEN_VERIFICACION_PRUEBA"
PHONE = "5491100000000"


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_text(self, to, text):
        self.sent.append((to, text))


def make():
    flow = load_flow(FIX)
    r = Responder(flow, Store(), Clock())
    s = FakeSender()
    return WebhookHandler(r, s, SECRET, VERIFY), s, r


def post(h, payload, secret=SECRET, raw=None):
    raw = raw if raw is not None else json.dumps(payload).encode()
    return h.handle_post(raw, wa.sign(raw, secret))


class VerifyTests(unittest.TestCase):
    def test_handshake(self):
        h, _, _ = make()
        self.assertEqual(h.handle_get({"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}), (200, "1158201444"))
        self.assertEqual(h.handle_get({"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1"})[0], 403)
        self.assertEqual(h.handle_get({"hub.mode": "unsubscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"})[0], 403)
        self.assertEqual(h.handle_get({"hub.mode": "subscribe", "hub.verify_token": VERIFY})[0], 400)
        self.assertEqual(h.handle_get({})[0], 403)

    def test_empty_configured_token_never_matches(self):
        self.assertEqual(wa.verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}, "")[0], 403)


class SignatureTests(unittest.TestCase):
    def test_valid_and_invalid_signatures(self):
        raw = b'{"a":1}'
        self.assertTrue(wa.verify_signature(raw, wa.sign(raw, SECRET), SECRET))
        self.assertFalse(wa.verify_signature(raw, wa.sign(raw, "otro_secreto"), SECRET))
        self.assertFalse(wa.verify_signature(b'{"a":2}', wa.sign(raw, SECRET), SECRET))   # cuerpo alterado
        self.assertFalse(wa.verify_signature(raw, None, SECRET))
        self.assertFalse(wa.verify_signature(raw, "", SECRET))
        self.assertFalse(wa.verify_signature(raw, wa.sign(raw, SECRET)[len("sha256="):], SECRET))  # sin prefijo
        self.assertFalse(wa.verify_signature(raw, "sha1=" + "0" * 40, SECRET))
        self.assertFalse(wa.verify_signature(raw, wa.sign(raw, SECRET), ""))  # sin secreto configurado

    def test_invalid_signature_is_rejected_and_nothing_is_processed(self):
        h, s, r = make()
        raw = json.dumps(example_payload("hola", PHONE)).encode()
        self.assertEqual(h.handle_post(raw, "sha256=" + "0" * 64)[0], 403)
        self.assertEqual(h.handle_post(raw, None)[0], 403)
        self.assertEqual(s.sent, [])
        self.assertIsNone(r.store.contact(PHONE))

    def test_valid_signature_but_bad_json_is_400(self):
        h, _, _ = make()
        self.assertEqual(post(h, None, raw=b"no es json")[0], 400)
        self.assertEqual(post(h, None, raw=b"[1,2]")[0], 400)


class IdempotencyTests(unittest.TestCase):
    def test_same_message_twice_is_processed_once(self):
        h, s, r = make()
        p = example_payload("hola", PHONE, msg_id="wamid.A")
        self.assertEqual(post(h, p)[0], 200)
        self.assertEqual(post(h, p)[0], 200)   # reintento o replay: 200 para que Meta no insista
        self.assertEqual(len(s.sent), 1)
        self.assertEqual(len([e for e in r.store.events(PHONE) if e["direction"] == "in"]), 1)

    def test_replay_of_old_signed_payload_is_blocked_by_message_id(self):
        h, s, _ = make()
        p = example_payload("hola", PHONE, msg_id="wamid.B", ts=1_000_000)
        post(h, p); post(h, p)
        self.assertEqual(len(s.sent), 1)

    def test_different_messages_are_both_processed(self):
        h, s, _ = make()
        post(h, example_payload("hola", PHONE, msg_id="wamid.1"))
        post(h, example_payload("sí", PHONE, msg_id="wamid.2"))
        self.assertEqual(len(s.sent), 2)


class FlowThroughWebhookTests(unittest.TestCase):
    def test_baja_and_human_exit_through_the_webhook(self):
        h, s, r = make()
        post(h, example_payload("hola", PHONE, msg_id="1"))
        post(h, example_payload("baja", PHONE, msg_id="2"))
        self.assertIsNotNone(r.store.contact(PHONE)["opt_out_at"])
        n = len(s.sent)
        post(h, example_payload("sí", PHONE, msg_id="3"))
        self.assertEqual(len(s.sent), n)  # silencio tras la baja
        post(h, example_payload("persona", "5491100000001", msg_id="4"))
        self.assertEqual(r.store.contact("5491100000001")["human"], 1)

    def test_first_reply_discloses_automatic_assistant(self):
        h, s, _ = make()
        post(h, example_payload("hola", PHONE))
        self.assertIn("asistente automático", s.sent[0][1])

    def test_status_only_and_unsupported_types_do_not_break(self):
        h, s, _ = make()
        status = {"object": "whatsapp_business_account", "entry": [{"id": "x", "changes": [{"field": "messages", "value": {"statuses": [{"id": "wamid.S", "status": "delivered"}]}}]}]}
        self.assertEqual(post(h, status)[0], 200)
        img = example_payload("", PHONE, msg_id="wamid.I")
        img["entry"][0]["changes"][0]["value"]["messages"][0].update(type="image")
        del img["entry"][0]["changes"][0]["value"]["messages"][0]["text"]
        self.assertEqual(post(h, img)[0], 200)  # no rompe; el respondedor lo trata como respuesta vacía

    def test_parse_inbound_matches_documented_structure(self):
        doc_example = {"object": "whatsapp_business_account", "entry": [{"id": "102290129340398", "changes": [{"value": {
            "messaging_product": "whatsapp", "metadata": {"display_phone_number": "15550783881", "phone_number_id": "106540352242922"},
            "contacts": [{"profile": {"name": "Sheena Nelson"}, "wa_id": "16505551234"}],
            "messages": [{"from": "16505551234", "id": "wamid.HBg", "timestamp": "1749416383", "type": "text",
                          "text": {"body": "Does it come in another color?"}}]}, "field": "messages"}]}]}
        (m,) = wa.parse_inbound(doc_example)
        self.assertEqual((m.sender, m.msg_id, m.timestamp, m.type, m.text),
                         ("16505551234", "wamid.HBg", 1749416383.0, "text", "Does it come in another color?"))
        self.assertEqual(wa.parse_inbound({"entry": [{"changes": [{"field": "otro", "value": {}}]}]}), [])
        self.assertEqual(wa.parse_inbound({}), [])


class FailingSender:
    def send_text(self, to, text):
        raise OSError("sin red")


class SendFailureTests(unittest.TestCase):
    def test_send_failure_is_logged_and_does_not_reprocess(self):
        flow = load_flow(FIX)
        r = Responder(flow, Store(), Clock())
        h = WebhookHandler(r, FailingSender(), SECRET, VERIFY)
        p = example_payload("hola", PHONE, msg_id="wamid.F")
        self.assertEqual(post(h, p)[0], 200)
        self.assertEqual(r.store.events(PHONE)[-1]["direction"], "envio_fallido")
        self.assertEqual(post(h, p)[0], 200)  # reintento de Meta: no duplica
        self.assertEqual(len([e for e in r.store.events(PHONE) if e["direction"] == "in"]), 1)


class SenderTests(unittest.TestCase):
    def test_text_and_template_requests(self):
        calls = []
        s = wa.CloudApiSender("PNID", "TOKEN_DE_PRUEBA_NO_REAL", "vXX.X", post=lambda *a: calls.append(a) or {"ok": 1})
        s.send_text("549", "hola")
        s.send_template("549", "seguimiento_24h", "es")
        url, headers, body = calls[0]
        self.assertEqual(url, "https://graph.facebook.com/vXX.X/PNID/messages")
        self.assertEqual(headers["Authorization"], "Bearer TOKEN_DE_PRUEBA_NO_REAL")
        self.assertEqual(body, {"messaging_product": "whatsapp", "to": "549", "type": "text", "text": {"body": "hola"}})
        self.assertEqual(calls[1][2], {"messaging_product": "whatsapp", "to": "549", "type": "template",
                                       "template": {"name": "seguimiento_24h", "language": {"code": "es"}}})

    def test_token_never_in_repr_and_env_required(self):
        s = wa.CloudApiSender("PNID", "TOKEN_DE_PRUEBA_NO_REAL", "vXX.X", post=lambda *a: None)
        self.assertNotIn("TOKEN_DE_PRUEBA_NO_REAL", repr(s))
        with self.assertRaises(ValueError) as cm:
            wa.CloudApiSender.from_env(env={"WHATSAPP_PHONE_NUMBER_ID": "x"})
        msg = str(cm.exception)
        self.assertIn("WHATSAPP_ACCESS_TOKEN", msg)
        self.assertIn("WHATSAPP_API_VERSION", msg)   # la versión no se inventa
        self.assertEqual(wa.missing_env({}), list(wa.ENV_REQUIRED))


if __name__ == "__main__":
    unittest.main()
