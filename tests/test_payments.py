import ast
import json
import os
import unittest

from engine import payments as pm
from engine.responder import Clock, Responder
from engine.store import Store
from engine.flow import load_flow
from tests.test_engine import FIX

SECRET = "SECRETO_MP_DE_PRUEBA_NO_REAL"
PHONE = "5491100000000"
CFG = {"price_ars": 1000, "item_title": "Producto de ejemplo ficticio", "notification_url": "https://ejemplo.invalid/mp",
       "delivery_failed_message": "No pudimos entregarte automáticamente. Escribí 'persona' o llamanos.", "delivery_max_attempts": 3}


class FakeSender:
    def __init__(self): self.sent = []
    def send_text(self, to, text): self.sent.append((to, text))


class FakeDeliverer:
    def __init__(self, fail_times=0):
        self.fail_times, self.calls, self.delivered = fail_times, 0, []
    def deliver(self, order):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise OSError("falla simulada")
        self.delivered.append(order["order_id"])


class FakeClient:
    """Simula la API de Mercado Pago: devuelve el pago que se le cargó."""
    def __init__(self): self.payments, self.fail = {}, False
    def get_payment(self, pid):
        if self.fail:
            raise OSError("sin red")
        return self.payments[pid]


def setup(fail_times=0, cfg=CFG):
    store = Store()
    orders = pm.Orders(store, pm.load_venture_config(cfg), clock=Clock().now)
    client, deliverer, sender = FakeClient(), FakeDeliverer(fail_times), FakeSender()
    handler = pm.PaymentHandler(orders, client, deliverer, sender, store, SECRET, sleep=lambda s: None)
    return store, orders, client, deliverer, sender, handler


def notif(handler, payment_id="111", live=False, secret=SECRET, req_id="req-1", ts="1700000000", type_="payment"):
    body = json.dumps({"action": "payment.updated", "api_version": "v1", "data": {"id": payment_id}, "date_created": "2026-10-08T00:00:00Z",
                       "id": "9", "live_mode": live, "type": type_, "user_id": 1}).encode()
    sig = pm.mp_sign(secret, payment_id, req_id, ts)
    return handler.handle({"data.id": payment_id, "type": type_}, {"x-signature": sig, "x-request-id": req_id}, body)


def approved(order, pid="111", amount=None, status="approved", currency="ARS"):
    return {"id": pid, "status": status, "external_reference": order["order_id"],
            "transaction_amount": order["amount"] if amount is None else amount, "currency_id": currency}


class ConfigTests(unittest.TestCase):
    def test_no_default_price(self):
        for bad in (None, 0, -5, "mil", True):
            with self.assertRaises(pm.ConfigError):
                pm.load_venture_config({**CFG, "price_ars": bad})
        c = dict(CFG); del c["price_ars"]
        with self.assertRaises(pm.ConfigError):
            pm.load_venture_config(c)

    def test_other_required_fields_and_https(self):
        with self.assertRaises(pm.ConfigError):
            pm.load_venture_config({**CFG, "notification_url": "http://x"})
        with self.assertRaises(pm.ConfigError):
            pm.load_venture_config({**CFG, "delivery_failed_message": ""})

    def test_order_amount_comes_from_config(self):
        _, orders, *_ = setup()
        self.assertEqual(orders.create(PHONE, "o1")["amount"], 1000)

    def test_test_mode_only_and_token_hidden(self):
        with self.assertRaises(pm.ConfigError):
            pm.MercadoPagoClient("TOKEN_DE_PRUEBA", "live")
        with self.assertRaises(pm.ConfigError):
            pm.MercadoPagoClient.from_env(env={"MP_MODE": "test"})
        c = pm.MercadoPagoClient("TOKEN_DE_PRUEBA_NO_REAL", "test", request=lambda *a: {})
        self.assertNotIn("TOKEN_DE_PRUEBA_NO_REAL", repr(c))

    def test_client_requests(self):
        calls = []
        c = pm.MercadoPagoClient("TOKEN_DE_PRUEBA_NO_REAL", "test", request=lambda *a: calls.append(a) or {"init_point": "https://pago.invalid/x"})
        _, orders, *_ = setup()
        o = orders.create(PHONE, "o1")
        self.assertEqual(c.create_preference(o, orders.cfg), "https://pago.invalid/x")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer TOKEN_DE_PRUEBA_NO_REAL")
        self.assertEqual(calls[0][3]["external_reference"], "o1")
        self.assertEqual(calls[0][3]["items"][0]["unit_price"], 1000)
        c.get_payment("111")
        self.assertEqual(calls[1][:2], ("GET", "https://api.mercadopago.com/v1/payments/111"))


class NotificationTests(unittest.TestCase):
    def test_valid_notification_delivers_once(self):
        store, orders, client, deliverer, sender, handler = setup()
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        self.assertEqual(notif(handler)[0], 200)
        self.assertEqual(deliverer.delivered, ["o1"])
        self.assertEqual(orders.get("o1")["status"], "entregado")
        kinds = [e["kind"] for e in orders.events("payment_events")]
        self.assertIn("aprobado", kinds)
        self.assertEqual([e["ok"] for e in orders.events("delivery_events")], [1])

    def test_duplicate_notification_does_not_deliver_twice(self):
        _, orders, client, deliverer, _, handler = setup()
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        notif(handler); r = notif(handler, req_id="req-2")
        self.assertEqual(r, (200, "ya procesado"))
        self.assertEqual(deliverer.calls, 1)

    def test_invalid_signature_is_rejected_and_nothing_happens(self):
        _, orders, client, deliverer, _, handler = setup()
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        self.assertEqual(notif(handler, secret="otro_secreto")[0], 401)
        self.assertEqual(handler.handle({"data.id": "111"}, {}, b'{"type":"payment","data":{"id":"111"}}')[0], 401)
        self.assertEqual(deliverer.calls, 0)
        self.assertEqual(orders.get("o1")["status"], "pendiente")
        self.assertIn("firma_invalida", [e["kind"] for e in orders.events("payment_events")])

    def test_signature_bound_to_data_id(self):
        _, orders, client, deliverer, _, handler = setup()
        o = orders.create(PHONE, "o1"); client.payments["222"] = approved(o, "222")
        body = json.dumps({"type": "payment", "live_mode": False, "data": {"id": "222"}}).encode()
        sig_for_other = pm.mp_sign(SECRET, "111", "req-1", "1700000000")
        self.assertEqual(handler.handle({"data.id": "222"}, {"x-signature": sig_for_other, "x-request-id": "req-1"}, body)[0], 401)
        self.assertEqual(deliverer.calls, 0)

    def test_not_approved_unknown_order_wrong_amount_and_live_mode_do_not_deliver(self):
        _, orders, client, deliverer, _, handler = setup()
        o = orders.create(PHONE, "o1")
        client.payments["1"] = approved(o, "1", status="pending")
        client.payments["2"] = {**approved(o, "2"), "external_reference": "no_existe"}
        client.payments["3"] = approved(o, "3", amount=1)
        client.payments["4"] = approved(o, "4", currency="USD")
        client.payments["5"] = approved(o, "5")
        for pid in "1234":
            self.assertEqual(notif(handler, payment_id=pid)[0], 200)
        self.assertEqual(notif(handler, payment_id="5", live=True)[0], 200)   # live_mode en modo de prueba
        self.assertEqual(deliverer.calls, 0)
        self.assertEqual(orders.get("o1")["status"], "pendiente")

    def test_non_payment_type_is_ignored_and_api_failure_asks_retry(self):
        _, orders, client, deliverer, _, handler = setup()
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        self.assertEqual(notif(handler, type_="plan")[0], 200)
        client.fail = True
        self.assertEqual(notif(handler)[0], 500)   # Mercado Pago reintenta
        client.fail = False
        self.assertEqual(notif(handler)[0], 200)   # y el reintento sí entrega
        self.assertEqual(deliverer.calls, 1)

    def test_bad_json_is_400(self):
        *_, handler = setup()
        self.assertEqual(handler.handle({}, {}, b"no es json")[0], 400)


class DeliveryTests(unittest.TestCase):
    def test_retries_then_succeeds(self):
        _, orders, client, deliverer, sender, handler = setup(fail_times=2)
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        notif(handler)
        self.assertEqual(orders.get("o1")["status"], "entregado")
        self.assertEqual([e["ok"] for e in orders.events("delivery_events")], [0, 0, 1])
        self.assertEqual(sender.sent, [])

    def test_persistent_failure_alerts_owner_and_tells_customer_how_to_reach_a_person(self):
        store, orders, client, deliverer, sender, handler = setup(fail_times=99)
        alerts = []
        orders.cfg["_notifier"] = alerts.append
        store.ensure(PHONE)
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        notif(handler)
        self.assertEqual(orders.get("o1")["status"], "entrega_fallida")
        self.assertEqual(deliverer.calls, 3)
        self.assertEqual(sender.sent, [(PHONE, CFG["delivery_failed_message"])])
        self.assertEqual(alerts, ["entrega fallida del pedido o1"])
        self.assertEqual(store.contact(PHONE)["human"], 1)
        self.assertEqual(orders.get("o1")["last_error"], "OSError")


class ClientMessageCannotForceDeliveryTests(unittest.TestCase):
    def test_responder_does_not_import_payments_or_delivery(self):
        root = os.path.join(os.path.dirname(__file__), "..", "engine")
        for fname in ("responder.py", "flow.py"):
            tree = ast.parse(open(os.path.join(root, fname)).read())
            mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
                   {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            self.assertFalse(any("payments" in (m or "") for m in mods), fname)

    def test_customer_messages_claiming_payment_change_nothing(self):
        store, orders, client, deliverer, sender, handler = setup()
        orders.create(PHONE, "o1")
        r = Responder(load_flow(FIX), store, Clock())
        for text in ("ya pagué", "te mando la captura del pago", "approved", "o1 pagado"):
            r.handle_incoming(PHONE, text)
        self.assertEqual(orders.get("o1")["status"], "pendiente")
        self.assertEqual(deliverer.calls, 0)


if __name__ == "__main__":
    unittest.main()


class ManifestOmissionTests(unittest.TestCase):
    def test_signature_omits_absent_request_id(self):
        import hashlib, hmac
        from engine.payments import verify_mp_signature
        v1 = hmac.new(b"k", b"id:123;ts:1700;", hashlib.sha256).hexdigest()
        self.assertTrue(verify_mp_signature("k", f"ts=1700,v1={v1}", None, "123"))
        self.assertFalse(verify_mp_signature("k", f"ts=1700,v1={v1}", "req-1", "123"))


class ReversalAndDuplicateTests(unittest.TestCase):
    def test_duplicate_approved_payment_is_not_delivered_twice_and_alerts(self):
        store, orders, client, deliverer, sender, handler = setup()
        alerts = []
        orders.cfg["_notifier"] = alerts.append
        store.ensure(PHONE)
        o = orders.create(PHONE, "o1")
        client.payments["111"] = approved(o)
        client.payments["222"] = approved(o, pid="222")
        notif(handler)
        notif(handler, payment_id="222", req_id="req-2")
        self.assertEqual(deliverer.calls, 1)
        self.assertEqual(len(alerts), 1)
        self.assertIn("duplicado", alerts[0])

    def test_refund_after_delivery_alerts_owner_and_changes_nothing(self):
        store, orders, client, deliverer, sender, handler = setup()
        alerts = []
        orders.cfg["_notifier"] = alerts.append
        store.ensure(PHONE)
        o = orders.create(PHONE, "o1")
        client.payments["111"] = approved(o)
        notif(handler)
        client.payments["111"] = approved(o, status="refunded")
        notif(handler, req_id="req-3")
        self.assertEqual(orders.get("o1")["status"], "entregado")
        self.assertEqual(len(alerts), 1)
        self.assertIn("revisar", alerts[0])


class RetryFailedTests(unittest.TestCase):
    def test_failed_delivery_is_retried_later_and_capped(self):
        store, orders, client, deliverer, sender, handler = setup(fail_times=3)
        store.ensure(PHONE)
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        notif(handler)
        self.assertEqual(orders.get("o1")["status"], "entrega_fallida")
        done = pm.retry_failed_deliveries(orders, deliverer, sender, store, sleep=lambda s: None)
        self.assertEqual(done, ["o1"])
        self.assertEqual(orders.get("o1")["status"], "entregado")

    def test_retry_rounds_are_capped(self):
        store, orders, client, deliverer, sender, handler = setup(fail_times=999)
        store.ensure(PHONE)
        o = orders.create(PHONE, "o1"); client.payments["111"] = approved(o)
        notif(handler)
        for _ in range(5):
            pm.retry_failed_deliveries(orders, deliverer, sender, store, max_rounds=2, sleep=lambda s: None)
        rondas = [e for e in orders.events("delivery_events") if e["note"] == "ronda_reintento"]
        self.assertEqual(len(rondas), 2)
        self.assertEqual(orders.get("o1")["status"], "entrega_fallida")
