"""Servidor local del webhook (stdlib). Solo para pruebas con un número de prueba.

  python -m engine.server <flow.yaml> [--port 8080] [--db conversaciones.sqlite]

Lee los secretos SOLO de variables de entorno (ver engine/whatsapp.py: ENV_REQUIRED).
Si falta alguna, avisa cuáles faltan (nunca imprime valores) y no arranca.
"""
import argparse
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import os

from engine import whatsapp as wa
from engine.flow import load_flow, validate_flow
from engine.notify import FileNotifier
from engine.responder import RealClock, Responder
from engine.store import Store
from engine.webhook import WebhookHandler


def make_server(handler, port):
    class H(BaseHTTPRequestHandler):
        timeout = 10  # un cliente lento no cuelga el servidor

        def _reply(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path != "/webhook":
                return self._reply(404, "no encontrado")
            params = {k: v[0] for k, v in parse_qs(u.query).items()}
            self._reply(*handler.handle_get(params))

        def do_POST(self):
            if urlparse(self.path).path != "/webhook":
                return self._reply(404, "no encontrado")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._reply(400, "largo inválido")
            if n < 0:
                return self._reply(400, "largo inválido")
            if n > 3 * 1024 * 1024:  # Meta documenta payloads de hasta 3 MB
                return self._reply(413, "demasiado grande")
            raw = self.rfile.read(n)
            self._reply(*handler.handle_post(raw, self.headers.get("X-Hub-Signature-256")))

        def log_message(self, fmt, *args):  # no se loguean cuerpos ni cabeceras
            sys.stderr.write("%s %s\n" % (self.command, urlparse(self.path).path))

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("flow")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--db", default="conversaciones.sqlite")
    ap.add_argument("--avisos", default="avisos.log", help="archivo donde se escriben los avisos al dueño")
    a = ap.parse_args(argv)
    miss = wa.missing_env()
    if miss:
        print("faltan variables de entorno: " + ", ".join(miss) + "\n(cargalas en tu entorno; nunca en un archivo del repo)")
        return 1
    flow = load_flow(a.flow)
    errs = validate_flow(flow)
    if errs:
        print("flow inválido:\n- " + "\n- ".join(errs))
        return 1
    h = WebhookHandler(Responder(flow, Store(a.db, threadsafe=True), RealClock(), notifier=FileNotifier(a.avisos)), wa.CloudApiSender.from_env(),
                       os.environ["WHATSAPP_APP_SECRET"], os.environ["WHATSAPP_VERIFY_TOKEN"])
    print(f"escuchando en http://127.0.0.1:{a.port}/webhook (Ctrl+C para salir)")
    make_server(h, a.port).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
