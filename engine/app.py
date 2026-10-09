"""Servidor de venta: whatsapp + cobro + entrega + descarga + verificación de clave.

  python -m engine.app ventures/<slug> [--port 8080] [--host 127.0.0.1] [--db tableproof.sqlite]

Rutas:
  GET  /webhook     verificación del webhook de whatsapp (Meta)
  POST /webhook     mensajes entrantes (firma X-Hub-Signature-256)
  POST /mp          notificaciones de Mercado Pago (firma x-signature + consulta a la API)
  GET  /d/<token>   descarga con link firmado (productos kind=download)
  GET  /verify?key= {"valid": true|false} (productos kind=access)
  GET  /health

Una sola conexión sqlite compartida: todo se serializa con un candado (alcanza para un MVP;
si crece, se separa). Lee los secretos SOLO del entorno (o de .env, que no se commitea).
El cobro hereda de engine/payments.py: sin precio del dueño no hay pedidos, y la guardia de
modo de prueba de ese módulo sigue como está (ver docs/mvp-punta-a-punta.md).
"""
import argparse
import json
import mimetypes
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import checkout as ck
from engine import delivery as dl
from engine import payments as pm
from engine import venture as vt
from engine import whatsapp as wa
from engine.envfile import load_env
from engine.flow import load_flow
from engine.notify import FileNotifier
from engine.responder import RealClock, Responder
from engine.store import Store
from engine.webhook import WebhookHandler

MAX_BODY = 3 * 1024 * 1024


class App:
    def __init__(self, venture_dir, env=None, db_path="tableproof.sqlite", avisos="avisos.log", sender=None, mp_request=None, clock=None):
        env = os.environ if env is None else env
        self.dir = venture_dir
        cfg = vt.load(venture_dir)
        self.cfg = pm.load_venture_config(cfg)
        self.kind = cfg["kind"]
        flow = load_flow(os.path.join(venture_dir, "flow.yaml"))
        self.store = Store(db_path, threadsafe=True)
        notifier = FileNotifier(avisos)
        self.orders = pm.Orders(self.store, self.cfg, notifier=notifier)
        client = pm.MercadoPagoClient.from_env(env, request=mp_request)
        inner = sender or wa.CloudApiSender.from_env(env)
        self.licenses = dl.Licenses(self.store.db)
        self.downloads = None
        if self.kind == "download":
            self.downloads = dl.DownloadService(
                self.store.db, env.get("DELIVERY_SECRET"), os.path.join(venture_dir, "entrega", cfg["file"]), cfg["public_base_url"],
                cfg.get("download_ttl_hours") or dl.DEFAULT_TTL_HOURS, cfg.get("download_max") or dl.DEFAULT_MAX_DOWNLOADS)
            deliverer = dl.DownloadDeliverer(self.licenses, self.downloads, inner, cfg)
        else:
            deliverer = dl.AccessDeliverer(self.licenses, inner, cfg)
        self.checkout = ck.Checkout(self.orders, client, self.cfg)
        outbound = ck.CheckoutSender(inner, self.checkout, cfg, notify=notifier)
        self.pay = pm.PaymentHandler(self.orders, client, deliverer, inner, self.store, env["MP_WEBHOOK_SECRET"])
        self.wa = WebhookHandler(Responder(flow, self.store, clock or RealClock(), notifier=notifier), outbound,
                                 env["WHATSAPP_APP_SECRET"], env["WHATSAPP_VERIFY_TOKEN"])
        self._lock = threading.Lock()

    def required_env(self):
        names = list(wa.ENV_REQUIRED) + list(pm.ENV_REQUIRED)
        return names + (["DELIVERY_SECRET"] if self.kind == "download" else [])

    # -> (status, content_type, body_bytes | ("file", path, filename))
    def route(self, method, raw_path, headers, body):
        u = urlparse(raw_path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        h = {k.lower(): v for k, v in headers.items()}
        with self._lock:
            if u.path == "/health":
                return 200, "text/plain; charset=utf-8", b"ok"
            if u.path == "/webhook" and method == "GET":
                s, t = self.wa.handle_get(q)
                return s, "text/plain; charset=utf-8", t.encode()
            if u.path == "/webhook" and method == "POST":
                s, t = self.wa.handle_post(body, h.get("x-hub-signature-256"))
                return s, "text/plain; charset=utf-8", t.encode()
            if u.path == "/mp" and method == "POST":
                s, t = self.pay.handle(q, h, body)
                return s, "text/plain; charset=utf-8", t.encode()
            if u.path == "/verify" and method == "GET":
                return 200, "application/json", json.dumps({"valid": self.licenses.verify(q.get("key"))}).encode()
            if u.path.startswith("/d/") and method == "GET" and self.downloads:
                status, _oid = self.downloads.authorize(u.path[3:])
                if status != 200:
                    return 403, "text/plain; charset=utf-8", b"link invalido, vencido o sin descargas disponibles"
                p = self.downloads.file_path
                if not os.path.exists(p):
                    return 500, "text/plain; charset=utf-8", b"archivo no disponible"
                return 200, mimetypes.guess_type(p)[0] or "application/octet-stream", ("file", p, os.path.basename(p))
        return 404, "text/plain; charset=utf-8", b"no encontrado"


def make_server(app, host, port):
    class H(BaseHTTPRequestHandler):
        timeout = 15

        def _go(self, method):
            n = 0
            if method == "POST":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n < 0 or n > MAX_BODY:
                    return self._send(413 if n > 0 else 400, "text/plain; charset=utf-8", b"cuerpo invalido")
            body = self.rfile.read(n) if n else b""
            self._send(*app.route(method, self.path, dict(self.headers.items()), body))

        def _send(self, status, ctype, body):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if isinstance(body, tuple):
                _, path, name = body
                self.send_header("Content-Length", str(os.path.getsize(path)))
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                with open(path, "rb") as f:
                    while chunk := f.read(1 << 20):
                        self.wfile.write(chunk)
                return
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, fmt, *args):  # sin cuerpos, cabeceras ni query (la query puede traer una clave)
            sys.stderr.write("%s %s\n" % (self.command, urlparse(self.path).path))

    return ThreadingHTTPServer((host, port), H)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("venture_dir")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "tableproof.sqlite"))
    a = ap.parse_args(argv)
    load_env()
    if not os.path.exists(os.path.join(a.venture_dir, "venture.yaml")):
        print(f"no hay venture.yaml en {a.venture_dir}")
        return 1
    res = vt.validate_all(a.venture_dir)
    problems = res["venta"] + res["flow"]
    pend = res["pendientes"]
    if problems or pend:
        print("no arranca; corré `python -m engine.check " + a.venture_dir + "` y resolvé:\n- " + "\n- ".join(problems + pend))
        return 1
    miss = [k for k in list(wa.ENV_REQUIRED) + list(pm.ENV_REQUIRED) if not os.environ.get(k)]
    if vt.load(a.venture_dir).get("kind") == "download" and not os.environ.get("DELIVERY_SECRET"):
        miss.append("DELIVERY_SECRET")
    if miss:
        print("faltan variables de entorno: " + ", ".join(miss) + "\n(en tu entorno o en .env; nunca en un archivo que se commitee)")
        return 1
    app = App(a.venture_dir, db_path=a.db)
    print(f"escuchando en http://{a.host}:{a.port} (Ctrl+C para salir)")
    make_server(app, a.host, a.port).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
