"""Pruebas del mvp de punta a punta: entrega, link de pago, anuncios y servidor. Sin red: todo con simulaciones."""
import base64
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse

import yaml

from engine import ads, app as app_mod, checkout as ck, delivery as dl
from engine import devtools, payments as pm, scaffold, venture as vt, whatsapp as wa
from engine.responder import Clock
from engine.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHONE = "5491100000000"
ENV = {"WHATSAPP_VERIFY_TOKEN": "verif-prueba", "WHATSAPP_APP_SECRET": "app-secret-prueba", "WHATSAPP_ACCESS_TOKEN": "tok-prueba",
       "WHATSAPP_PHONE_NUMBER_ID": "123", "WHATSAPP_API_VERSION": "v0.0", "MP_ACCESS_TOKEN": "TEST-prueba",
       "MP_WEBHOOK_SECRET": "mp-secret-prueba", "MP_MODE": "test", "DELIVERY_SECRET": "entrega-secreto-de-prueba"}
BASE = {"name": "Producto ficticio", "price_ars": 1000, "item_title": "Producto ficticio", "public_base_url": "https://ejemplo.invalid",
        "notification_url": "https://ejemplo.invalid/mp", "delivery_failed_message": "fallo, escribí persona",
        "already_paid_message": "ya pagaste", "checkout_failed_message": "no pudimos generar el link"}
ADS_CFG = {"whatsapp_number": "5491100000000", "countries": ["AR"], "daily_budget": 12.5, "age_min": 25,
           "prefilled_message": "Hola, quiero info",
           "variants": [{"headline": "Titular uno", "primary_text": "Texto uno", "image_prompt": "un escritorio ordenado", "aspect_ratio": "1:1"},
                        {"headline": "Titular dos", "primary_text": "Texto dos", "image_prompt": "una laptop", "aspect_ratio": "4:5"}]}


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_text(self, to, text):
        self.sent.append((to, text))

    def send_template(self, *a, **k):
        self.sent.append(("tpl", a))


def paid_order_db(order_id="o1", status="pagado"):
    store = Store()
    orders = pm.Orders(store, pm.load_venture_config(BASE), clock=Clock().now)
    orders.create(PHONE, order_id)
    orders.update(order_id, status=status)
    return store, orders


class DeliveryTests(unittest.TestCase):
    def test_key_is_issued_once_per_order_and_verifies_only_when_paid(self):
        store, orders = paid_order_db(status="pendiente")
        lic = dl.Licenses(store.db)
        key = lic.issue("o1")
        self.assertRegex(key, r"^TP-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$")
        self.assertEqual(lic.issue("o1"), key)
        self.assertFalse(lic.verify(key))  # pedido todavía pendiente
        orders.update("o1", status="entregado")
        self.assertTrue(lic.verify(key))
        self.assertFalse(lic.verify("TP-NO-EXISTE"))
        self.assertTrue(lic.revoke(key))
        self.assertFalse(lic.verify(key))

    def test_access_deliverer_sends_once(self):
        store, orders = paid_order_db()
        sender = FakeSender()
        d = dl.AccessDeliverer(dl.Licenses(store.db), sender, {"delivery_message": "Clave: {key} en {url}", "access_url": "https://x.invalid"})
        order = orders.get("o1")
        d.deliver(order)
        d.deliver(order)  # reintento: no duplica
        self.assertEqual(len(sender.sent), 1)
        self.assertIn("TP-", sender.sent[0][1])
        self.assertEqual(sender.sent[0][0], PHONE)

    def test_tokens_expire_and_reject_tampering(self):
        t = dl.make_token("s", "o1", 1000)
        self.assertEqual(dl.parse_token("s", t, 999), "o1")
        self.assertIsNone(dl.parse_token("s", t, 1001))
        self.assertIsNone(dl.parse_token("otro", t, 999))
        self.assertIsNone(dl.parse_token("s", t[:-1] + ("0" if t[-1] != "0" else "1"), 999))
        for bad in ("", "x", "a.b", None):
            self.assertIsNone(dl.parse_token("s", bad, 0))

    def test_download_limit_and_unpaid_orders(self):
        store, orders = paid_order_db()
        now = [100.0]
        svc = dl.DownloadService(store.db, "s", "/tmp/x", "https://h.invalid", ttl_hours=1, max_downloads=2, clock=lambda: now[0])
        token = svc.url_for("o1").rsplit("/d/", 1)[1]
        self.assertEqual(svc.authorize(token), (200, "o1"))
        self.assertEqual(svc.authorize(token), (200, "o1"))
        self.assertEqual(svc.authorize(token)[0], 403)  # tope de descargas
        orders.update("o1", status="pendiente")
        store2, orders2 = paid_order_db("o2", "pendiente")
        svc2 = dl.DownloadService(store2.db, "s", "/tmp/x", "https://h.invalid", clock=lambda: now[0])
        self.assertEqual(svc2.authorize(svc2.url_for("o2").rsplit("/d/", 1)[1])[0], 403)  # sin pago, sin descarga
        now[0] += 3601 * 10
        self.assertEqual(svc.authorize(token)[0], 403)  # vencido

    def test_download_service_requires_a_secret(self):
        with self.assertRaises(ValueError):
            dl.DownloadService(Store().db, "", "/tmp/x", "https://h.invalid")


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.cfg = {**BASE}
        self.orders = pm.Orders(self.store, pm.load_venture_config(self.cfg), clock=Clock().now)
        self.created = []

        class Client:
            def create_preference(inner, order, cfg):
                self.created.append(order["order_id"])
                return f"https://mp.invalid/pay/{order['order_id']}"
        self.checkout = ck.Checkout(self.orders, Client(), self.cfg)

    def test_one_pending_order_per_phone_and_paid_blocks(self):
        a = self.checkout.link_for(PHONE)
        self.assertEqual(self.checkout.link_for(PHONE), a)
        self.assertEqual(len(self.created), 1)
        self.orders.update(self.created[0], status="pagado")
        self.assertIsNone(self.checkout.link_for(PHONE))

    def test_repeat_purchase_allows_a_new_order_only_after_delivery(self):
        self.cfg["repeat_purchase"] = True
        a = self.checkout.link_for(PHONE)
        self.orders.update(self.created[0], status="pagado")
        self.assertIsNone(self.checkout.link_for(PHONE))  # pagado sin entregar: no se cobra otra vez
        self.orders.update(self.created[0], status="entrega_fallida")
        self.assertIsNone(self.checkout.link_for(PHONE))
        self.orders.update(self.created[0], status="entregado")
        b = self.checkout.link_for(PHONE)
        self.assertNotEqual(a, b)
        self.assertEqual(self.checkout.link_for(PHONE), b)  # el pedido nuevo pendiente reutiliza su link
        self.assertEqual(len(self.created), 2)

    def test_repeat_purchase_must_be_a_real_boolean(self):
        self.cfg["repeat_purchase"] = "true"
        self.checkout.link_for(PHONE)
        self.orders.update(self.created[0], status="entregado")
        self.assertIsNone(self.checkout.link_for(PHONE))
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self.assertIn("repeat_purchase debe ser true o false", vt.validate_sale({**BASE, "kind": "access", "repeat_purchase": "si"}, d))

    def test_sender_replaces_token_and_falls_back_on_failure(self):
        inner, notes = FakeSender(), []
        s = ck.CheckoutSender(inner, self.checkout, self.cfg, notify=notes.append)
        s.send_text(PHONE, "Pagá acá: {pay_link}")
        self.assertTrue(inner.sent[0][1].startswith("Pagá acá: https://mp.invalid/pay/"))
        s.send_text(PHONE, "sin link")
        self.assertEqual(inner.sent[1][1], "sin link")
        self.orders.update(self.created[0], status="entregado")
        s.send_text(PHONE, "Pagá acá: {pay_link}")
        self.assertEqual(inner.sent[2][1], "ya pagaste")

        class Boom:
            def link_for(self, phone):
                raise OSError("sin red")
        s2 = ck.CheckoutSender(FakeSender(), Boom(), self.cfg, notify=notes.append)
        s2.send_text("5491122223333", "{pay_link}")
        self.assertEqual(s2.inner.sent[0][1], "no pudimos generar el link")
        self.assertEqual(len(notes), 1)
        self.assertNotIn("5491122223333", notes[0])  # teléfono enmascarado


class AdsTests(unittest.TestCase):
    def cfg(self):
        return {"name": "Producto ficticio", "ads": json.loads(json.dumps(ADS_CFG))}

    def test_copy_guard(self):
        self.assertIn("garantizado", ads.copy_problems("Ingreso GARANTIZADO desde casa"))
        self.assertEqual(ads.copy_problems("Una herramienta para ordenar tus pedidos"), [])
        self.assertEqual(ads.copy_problems("promo especial", extra=["promo especial"]), ["promo especial"])

    def test_plan_has_owner_numbers_and_is_paused(self):
        plan = ads.build_plan(self.cfg())
        self.assertEqual(plan["campaign"]["status"], "PAUSED")
        self.assertEqual(plan["adset"]["status"], "PAUSED")
        self.assertEqual(plan["adset"]["daily_budget"], 1250)
        self.assertEqual(plan["adset"]["targeting"]["geo_locations"]["countries"], ["AR"])
        self.assertEqual(plan["adset"]["targeting"]["age_min"], 25)
        self.assertEqual(len(plan["creatives"]), 2)
        link = plan["creatives"][0]["object_story_spec"]["link_data"]["link"]
        self.assertTrue(link.startswith("https://api.whatsapp.com/send?phone=5491100000000&text="))

    def test_gemini_parses_both_response_shapes_and_hides_key(self):
        png = base64.b64encode(b"PNGDATA").decode()
        seen = {}

        def req(method, url, headers, body):
            seen["url"], seen["headers"], seen["body"] = url, headers, json.loads(body)
            return {"candidates": [{"content": {"parts": [{"text": "hola"}, {"inlineData": {"mimeType": "image/png", "data": png}}]}}]}
        g = ads.GeminiImages("CLAVE-GEMINI-DE-PRUEBA", "modelo-x", request=req)
        self.assertEqual(g.generate("una taza", "4:5"), (b"PNGDATA", "image/png"))
        self.assertIn("modelo-x:generateContent", seen["url"])
        self.assertEqual(seen["headers"]["x-goog-api-key"], "CLAVE-GEMINI-DE-PRUEBA")
        self.assertEqual(seen["body"]["generationConfig"]["imageConfig"]["aspectRatio"], "4:5")
        self.assertIn("sin texto", seen["body"]["contents"][0]["parts"][0]["text"])
        self.assertNotIn("CLAVE-GEMINI", repr(g))
        g2 = ads.GeminiImages("k", "m", api="interactions", request=lambda *a: {"output_image": {"data": png}})
        self.assertEqual(g2.generate("x"), (b"PNGDATA", "image/jpeg"))
        with self.assertRaises(ads.AdsError):
            ads.GeminiImages("k", "m", request=lambda *a: {"candidates": []}).generate("x")
        with self.assertRaises(ads.AdsError):
            ads.GeminiImages.from_env(env={})

    def make_meta(self):
        calls = []

        def req(method, url, headers, body):
            fields = dict(urllib.parse.parse_qsl(body.decode()))
            calls.append((url, fields))
            if url.endswith("/adimages"):
                return {"images": {"bytes": {"hash": "HASH1"}}}
            return {"id": f"id{len(calls)}"}
        return ads.MetaAds("TOKEN-META-DE-PRUEBA", "999", "PAGE1", "v0.0", request=req), calls

    def test_create_makes_everything_paused_and_activate_needs_confirmation(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "ads"))
        for i in (1, 2):
            open(os.path.join(d, "ads", f"variante-{i}.png"), "wb").write(b"img")
        meta, calls = self.make_meta()
        cfg = self.cfg()
        ids = ads.create_campaign(d, cfg, meta, out=lambda *a: None)
        urls = [c[0].split("/v0.0/")[1] for c in calls]
        self.assertEqual(urls, ["act_999/campaigns", "act_999/adsets", "act_999/adimages", "act_999/adcreatives", "act_999/ads",
                                "act_999/adimages", "act_999/adcreatives", "act_999/ads"])
        self.assertEqual(calls[0][1]["status"], "PAUSED")
        self.assertEqual(calls[1][1]["status"], "PAUSED")
        self.assertEqual(json.loads(calls[1][1]["promoted_object"])["page_id"], "PAGE1")
        self.assertIn("HASH1", calls[3][1]["object_story_spec"])
        self.assertEqual(calls[4][1]["status"], "PAUSED")
        self.assertTrue(all(f["access_token"] == "TOKEN-META-DE-PRUEBA" for _, f in calls))
        self.assertTrue(all("TOKEN-META" not in u for u, _ in calls))  # el token va en el cuerpo, no en la URL
        self.assertNotIn("TOKEN-META", repr(meta))
        with self.assertRaises(ads.AdsError):
            ads.create_campaign(d, cfg, meta)  # ya hay campaña: no crea otra
        with self.assertRaises(ads.AdsError):
            ads.activate(d, cfg, meta, confirmed=False)
        before = len(calls)
        ads.activate(d, cfg, meta, confirmed=True, out=lambda *a: None)
        self.assertEqual(len(calls) - before, len(ids["ads"]) + 2)
        self.assertTrue(all(f["status"] == "ACTIVE" for _, f in calls[before:]))

    def test_create_refuses_risky_copy_and_missing_images(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        meta, calls = self.make_meta()
        with self.assertRaises(ads.AdsError):
            ads.create_campaign(d, self.cfg(), meta)  # faltan imágenes
        cfg = self.cfg()
        cfg["ads"]["variants"][0]["primary_text"] = "Plata fácil, sin riesgo"
        with self.assertRaises(ads.AdsError):
            ads.create_campaign(d, cfg, meta)
        self.assertEqual(calls, [])

    def test_missing_owner_numbers_never_reach_meta(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "ads"))
        for i in (1, 2):
            open(os.path.join(d, "ads", f"variante-{i}.png"), "wb").write(b"img")
        meta, calls = self.make_meta()
        for field, value in (("daily_budget", None), ("countries", [])):
            cfg = self.cfg()
            cfg["ads"][field] = value
            self.assertIsNone(ads.build_plan({**cfg, "ads": {**cfg["ads"], "daily_budget": None}})["adset"]["daily_budget"])
            with self.assertRaises(ads.AdsError):
                ads.create_campaign(d, cfg, meta)
        self.assertEqual(calls, [])

    def test_plan_command_works_before_the_owner_sets_the_budget(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        cfg = self.cfg()
        cfg["ads"]["daily_budget"] = None
        with open(os.path.join(d, "venture.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ads.main(["plan", d]), 1)
        self.assertIn("ads.daily_budget", out.getvalue())
        self.assertIn('"daily_budget": null', out.getvalue())

    def test_images_are_not_regenerated(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        n = []

        class G:
            def generate(self, prompt, ratio):
                n.append(prompt)
                return b"x", "image/jpeg"
        ads.generate_images(d, self.cfg(), G(), out=lambda *a: None)
        ads.generate_images(d, self.cfg(), G(), out=lambda *a: None)
        self.assertEqual(len(n), 2)
        self.assertTrue(os.path.exists(os.path.join(d, "ads", "variante-1.jpg")))


def write_venture(d, kind="access", extra=None):
    os.makedirs(d, exist_ok=True)
    cfg = {**BASE, "kind": kind}
    if kind == "access":
        cfg.update(access_url="https://app.ejemplo.invalid", delivery_message="Tu clave: {key}\nAcceso: {url}")
    else:
        cfg.update(file="producto.exe", delivery_message="Descargá: {url}")
        os.makedirs(os.path.join(d, "entrega"), exist_ok=True)
        open(os.path.join(d, "entrega", "producto.exe"), "wb").write(b"MZ-contenido-de-prueba")
    cfg.update(extra or {})
    yaml.safe_dump(cfg, open(os.path.join(d, "venture.yaml"), "w", encoding="utf-8"), allow_unicode=True)
    flow = yaml.safe_load(open(os.path.join(ROOT, "ventures", "_plantilla", "flow.yaml"), encoding="utf-8").read().replace("[completar: nombre del emprendimiento]", "Producto ficticio")
                          .replace("[completar: marca]", "Marca Ficticia").replace("[completar: qué es el producto en una línea]", "Es un producto ficticio")
                          .replace("[completar: oferta en una línea, lo que NO garantiza, y cómo se entrega]", "Oferta ficticia"))
    yaml.safe_dump(flow, open(os.path.join(d, "flow.yaml"), "w", encoding="utf-8"), allow_unicode=True)
    return d


class VentureTests(unittest.TestCase):
    def test_template_is_blocked_until_completed(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        os.makedirs(os.path.join(root, "ventures"))
        shutil.copytree(os.path.join(ROOT, "ventures", "_plantilla"), os.path.join(root, "ventures", "_plantilla"))
        src = os.path.join(root, "ing.json")
        json.dump({"ingredients": [{"id": "chatbase", "name": "Chatbase", "automation": {}}]}, open(src, "w"))
        for kind in ("access", "download"):
            dest = scaffold.scaffold("chatbase", src, kind=kind, slug=f"cb-{kind}", root=root)
            res = vt.validate_all(dest)
            self.assertTrue(res["pendientes"])
            self.assertTrue(any("price_ars" in e for e in res["venta"]))
            self.assertTrue(any("daily_budget" in e for e in res["anuncios"]))
            self.assertIn("Chatbase", open(os.path.join(dest, "venture.yaml"), encoding="utf-8").read())
        with self.assertRaises(ValueError):
            scaffold.scaffold("chatbase", src, slug="cb-access", root=root)  # ya existe
        with self.assertRaises(ValueError):
            scaffold.scaffold("no-existe", src, root=root)

    def test_complete_venture_passes_and_sale_rules_are_enforced(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        write_venture(d, "access", {"ads": ADS_CFG})
        res = vt.validate_all(d)
        self.assertEqual({k: v for k, v in res.items() if v}, {})
        bad = write_venture(tempfile.mkdtemp(), "access", {"delivery_message": "sin clave", "price_ars": None})
        self.addCleanup(shutil.rmtree, bad)
        errs = vt.validate_all(bad)["venta"]
        self.assertTrue(any("{key}" in e for e in errs) and any("price_ars" in e for e in errs))
        dd = write_venture(tempfile.mkdtemp(), "download")
        self.addCleanup(shutil.rmtree, dd)
        os.remove(os.path.join(dd, "entrega", "producto.exe"))
        self.assertTrue(any("entrega/producto.exe" in e for e in vt.validate_all(dd)["venta"]))

    def test_flow_needs_the_pay_link(self):
        d = write_venture(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        flow = yaml.safe_load(open(os.path.join(d, "flow.yaml"), encoding="utf-8"))
        flow["states"]["oferta"]["message"] = "Oferta sin link"
        yaml.safe_dump(flow, open(os.path.join(d, "flow.yaml"), "w", encoding="utf-8"), allow_unicode=True)
        self.assertTrue(any("{pay_link}" in e for e in vt.validate_all(d)["flow"]))


class EndToEnd(unittest.TestCase):
    """whatsapp -> link de pago -> notificación de Mercado Pago -> entrega automática."""

    def build(self, kind):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        write_venture(d, kind)
        self.pending = {}
        self.sender = FakeSender()

        def mp(method, url, headers, body):
            if url.endswith("/checkout/preferences"):
                ref = body["external_reference"]  # el cliente de payments.py manda un dict
                self.pending[ref] = body["items"][0]["unit_price"]
                return {"init_point": f"https://mp.invalid/pay/{ref}"}
            pid = url.rsplit("/", 1)[1]
            ref = self.paying[pid]
            return {"id": pid, "status": "approved", "external_reference": ref, "transaction_amount": self.pending[ref], "currency_id": "ARS"}
        self.paying = {}
        db = os.path.join(d, "t.sqlite")
        return app_mod.App(d, env=ENV, db_path=db, avisos=os.path.join(d, "avisos.log"), sender=self.sender, mp_request=mp), d

    def say(self, app, text, n):
        raw = json.dumps(devtools.example_payload(text, PHONE, msg_id=f"wamid.T{n}")).encode()
        return app.route("POST", "/webhook", {"X-Hub-Signature-256": wa.sign(raw, ENV["WHATSAPP_APP_SECRET"])}, raw)

    def pay(self, app, pid, ref, req_id="r1"):
        self.paying[pid] = ref
        raw = json.dumps({"type": "payment", "live_mode": False, "data": {"id": pid}, "action": "payment.updated"}).encode()
        sig = pm.mp_sign(ENV["MP_WEBHOOK_SECRET"], pid, req_id, "1700000000")
        return app.route("POST", f"/mp?data.id={pid}&type=payment", {"x-signature": sig, "x-request-id": req_id}, raw)

    def test_access_product_sold_and_delivered_automatically(self):
        app, _ = self.build("access")
        self.assertEqual(self.say(app, "hola", 1)[0], 200)
        self.say(app, "si", 2)
        offer = self.sender.sent[-1][1]
        self.assertIn("https://mp.invalid/pay/", offer)
        ref = offer.rsplit("/", 1)[1].strip()
        self.assertEqual(self.pay(app, "111", ref)[0], 200)
        key_msg = self.sender.sent[-1][1]
        self.assertIn("TP-", key_msg)
        key = key_msg.split("Tu clave: ")[1].split("\n")[0]
        self.assertEqual(json.loads(app.route("GET", f"/verify?key={key}", {}, b"")[2]), {"valid": True})
        self.assertEqual(json.loads(app.route("GET", "/verify?key=TP-FALSA", {}, b"")[2]), {"valid": False})
        n = len(self.sender.sent)
        self.pay(app, "111", ref)  # notificación repetida: no entrega dos veces
        self.assertEqual(len(self.sender.sent), n)
        self.say(app, "si", 3)  # ya pagó: no se crea otro pedido
        self.assertEqual(len(self.pending), 1)

    def test_unsigned_payment_notification_never_delivers(self):
        app, _ = self.build("access")
        self.say(app, "hola", 1)
        self.say(app, "si", 2)
        ref = self.sender.sent[-1][1].rsplit("/", 1)[1].strip()
        self.paying["9"] = ref
        raw = json.dumps({"type": "payment", "live_mode": False, "data": {"id": "9"}}).encode()
        status = app.route("POST", "/mp?data.id=9", {"x-signature": "ts=1,v1=00", "x-request-id": "r"}, raw)[0]
        self.assertEqual(status, 401)
        self.assertFalse(any("TP-" in t for _, t in self.sender.sent))

    def test_download_product_serves_the_file_with_a_signed_link(self):
        app, d = self.build("download")
        self.say(app, "hola", 1)
        self.say(app, "si", 2)
        ref = self.sender.sent[-1][1].rsplit("/", 1)[1].strip()
        self.pay(app, "222", ref)
        url = self.sender.sent[-1][1].split("Descargá: ")[1].strip()
        path = "/d/" + url.rsplit("/d/", 1)[1]
        status, ctype, body = app.route("GET", path, {}, b"")
        self.assertEqual(status, 200)
        self.assertEqual(body[0], "file")
        self.assertEqual(open(body[1], "rb").read(), b"MZ-contenido-de-prueba")
        self.assertEqual(app.route("GET", "/d/invalido.firma", {}, b"")[0], 403)
        self.assertEqual(app.route("GET", "/nada", {}, b"")[0], 404)
        self.assertEqual(app.route("GET", "/health", {}, b"")[0], 200)


if __name__ == "__main__":
    unittest.main()
