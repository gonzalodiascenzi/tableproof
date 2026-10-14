"""Servidor del producto: panel del dueño del bot, chat, widget para la web y demo pública.

  python ventures/chatbots-saas/producto/server.py [--port 8090] [--host 127.0.0.1] [--db chatbot.sqlite]
  python ventures/chatbots-saas/producto/server.py uso [--db chatbot.sqlite]     # mensajes y tokens por bot y por día

Rutas:
  GET  /             panel: con la clave se carga la info del negocio y se obtiene el código para pegar en la web
  GET  /demo         página de ejemplo con el widget y un negocio ficticio
  GET  /widget.js    el widget (se pega en la web del cliente)
  POST /api/bot/load {"key"} -> {"bot_id","name","content","balance"}
  POST /api/bot      {"key","name","content"} -> {"bot_id"}
  POST /api/bot/recarga {"key","new_key"} -> {"balance"}   suma el paquete de otra clave paga
  POST /api/chat     {"bot_id","message","history"} -> {"reply"}   (CORS abierto: lo llama el widget desde otra web)
  GET  /health

Variables de entorno (o .env, que no se commitea):
  ANTHROPIC_API_KEY        clave de la API de Claude
  TABLEPROOF_VERIFY_URL    url del /verify del servidor de venta, por ejemplo https://<dominio>/verify
  CHATBOT_PACK_MESSAGES    consultas que vale cada clave paga (lo define el dueño; sin valor por defecto)
  CHATBOT_MODEL            opcional (por defecto: ver bot.DEFAULT_MODEL)
  CHATBOT_TRUST_FORWARDED  opcional: 1 si hay un proxy propio adelante que escribe X-Forwarded-For
  topes opcionales: ver bot.DEFAULTS
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import bot as bot_mod  # noqa: E402
from engine.envfile import load_env  # noqa: E402

MAX_BODY = 256 * 1024
ENV_REQUIRED = ("ANTHROPIC_API_KEY", "TABLEPROOF_VERIFY_URL", bot_mod.PACK_ENV)
STATIC = {"/": ("panel.html", "text/html; charset=utf-8"), "/demo": ("demo.html", "text/html; charset=utf-8"),
          "/widget.js": ("widget.js", "text/javascript; charset=utf-8")}
JSON = "application/json; charset=utf-8"


def http_verifier(verify_url):
    def verify(key):
        try:
            with urllib.request.urlopen(f"{verify_url}?{urllib.parse.urlencode({'key': key})}", timeout=10) as r:
                return json.loads(r.read().decode()).get("valid") is True
        except (OSError, ValueError):
            return False  # si el servidor de venta no contesta, no se da acceso
    return verify


def load_demo(path=os.path.join(HERE, "demo_contenido.md")):
    with open(path, encoding="utf-8") as f:
        return {"name": "Vivero Ejemplo (ficticio)", "content": f.read()}


class App:
    def __init__(self, chatbot):
        self.bot = chatbot

    # -> (status, content_type, body_bytes)
    def route(self, method, raw_path, body, ip):
        path = urllib.parse.urlparse(raw_path).path
        if path == "/health":
            return 200, "text/plain; charset=utf-8", b"ok"
        if method == "GET" and path in STATIC:
            name, ctype = STATIC[path]
            with open(os.path.join(HERE, "static", name), "rb") as f:
                return 200, ctype, f.read()
        if method == "POST" and path in ("/api/bot/load", "/api/bot", "/api/bot/recarga", "/api/chat"):
            try:
                d = json.loads(body.decode() or "{}")
                if not isinstance(d, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                return 400, JSON, json.dumps({"error": "json inválido"}).encode()
            try:
                if path == "/api/bot/load":
                    out = self.bot.load_bot(d.get("key"))
                elif path == "/api/bot":
                    out = {"bot_id": self.bot.save_bot(d.get("key"), d.get("name"), d.get("content"))}
                elif path == "/api/bot/recarga":
                    out = {"balance": self.bot.top_up(d.get("key"), d.get("new_key"))}
                else:
                    out = {"reply": self.bot.chat(d.get("bot_id"), d.get("message"), d.get("history"), ip)}
            except bot_mod.ChatError as e:
                return e.status, JSON, json.dumps({"error": e.message}).encode()
            return 200, JSON, json.dumps(out).encode()
        return 404, "text/plain; charset=utf-8", b"no encontrado"


def make_server(app, host, port, trust_forwarded=False):
    class H(BaseHTTPRequestHandler):
        timeout = 60

        def _ip(self):
            fwd = self.headers.get("X-Forwarded-For") if trust_forwarded else None
            return fwd.split(",")[-1].strip() if fwd else self.client_address[0]

        def _go(self, method):
            n = 0
            if method == "POST":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n < 0 or n > MAX_BODY:
                    return self._send(413 if n > 0 else 400, "text/plain; charset=utf-8", b"cuerpo invalido")
            self._send(*app.route(method, self.path, self.rfile.read(n) if n else b"", self._ip()))

        def _send(self, status, ctype, body):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _cors(self):  # solo el chat se llama desde otras webs; el panel se usa desde este mismo origen
            if urllib.parse.urlparse(self.path).path == "/api/chat":
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt, *args):  # sin cuerpos ni query
            sys.stderr.write("%s %s\n" % (self.command, urllib.parse.urlparse(self.path).path))

    return ThreadingHTTPServer((host, port), H)


def print_usage(db_path):
    import sqlite3
    if not os.path.exists(db_path):
        print(f"no existe {db_path}")
        return 1
    rows = sqlite3.connect(db_path).execute("SELECT bot_id, day, messages, input_tokens, output_tokens FROM usage ORDER BY day, bot_id").fetchall()
    print("bot | día | mensajes | tokens entrada | tokens salida")
    for r in rows:
        print(" | ".join(str(x) for x in r))
    if not rows:
        print("(sin datos)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["uso"])
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("CHATBOT_PORT", "8090")))
    ap.add_argument("--db", default=os.environ.get("CHATBOT_DB_PATH", "chatbot.sqlite"))
    a = ap.parse_args(argv)
    if a.cmd == "uso":
        return print_usage(a.db)
    load_env()
    miss = [k for k in ENV_REQUIRED if not os.environ.get(k)]
    if miss:
        print("faltan variables de entorno: " + ", ".join(miss) + "\n(en tu entorno o en .env; nunca en un archivo que se commitee)")
        return 1
    try:
        limits = bot_mod.limits_from_env(os.environ)
        pack = int(os.environ[bot_mod.PACK_ENV])
        answerer = bot_mod.ClaudeAnswerer(os.environ.get("CHATBOT_MODEL") or bot_mod.DEFAULT_MODEL)
        chatbot = bot_mod.Chatbot(a.db, answerer, http_verifier(os.environ["TABLEPROOF_VERIFY_URL"]), pack, demo=load_demo(), limits=limits)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print(f"escuchando en http://{a.host}:{a.port} (Ctrl+C para salir)")
    make_server(App(chatbot), a.host, a.port, os.environ.get("CHATBOT_TRUST_FORWARDED") == "1").serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
