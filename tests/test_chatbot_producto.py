"""Pruebas del producto de ventures/chatbots-saas (chatbot con la info del negocio). Sin red: modelo y licencias simulados."""
import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTO = os.path.join(ROOT, "ventures", "chatbots-saas", "producto")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"chatbot_producto_{name}", os.path.join(PRODUCTO, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = _load("server")
bot = server.bot_mod
KEY = "TP-AAAA-BBBB-CCCC-DDDD"
DEMO = {"name": "Negocio ficticio", "content": "Abrimos de 9 a 18 (dato ficticio)."}


class FakeAnswerer:
    def __init__(self, reply="respuesta simulada", fail=False):
        self.calls, self.reply, self.fail = [], reply, fail

    def answer(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise RuntimeError("caída simulada")
        return self.reply, 100, 20


class FakeClock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


KEY2 = "TP-EEEE-FFFF-0000-1111"


def make(valid=(KEY,), limits=None, answerer=None, demo=DEMO, db=":memory:", pack=50):
    valid = set(valid)
    ans = answerer or FakeAnswerer()
    clock = FakeClock()
    cb = bot.Chatbot(db, ans, lambda k: k in valid, pack, demo=demo, limits=limits, clock=clock)
    return cb, ans, clock, valid


class LicenciaYPanel(unittest.TestCase):
    def test_sin_clave_valida_no_se_guarda_ni_se_carga(self):
        cb, _, _, _ = make()
        for key in ("TP-NO-EXISTE", "", None):
            with self.assertRaises(bot.ChatError) as e:
                cb.save_bot(key, "Mi negocio", "info")
            self.assertEqual(e.exception.status, 403)
            with self.assertRaises(bot.ChatError):
                cb.load_bot(key)

    def test_guardar_dos_veces_conserva_el_mismo_bot(self):
        cb, _, _, _ = make()
        self.assertEqual(cb.load_bot(KEY)["bot_id"], None)
        a = cb.save_bot(KEY, "Mi negocio", "info uno")
        b = cb.save_bot(KEY, "Mi negocio", "info dos")
        self.assertEqual(a, b)
        self.assertEqual(cb.load_bot(KEY), {"bot_id": a, "name": "Mi negocio", "content": "info dos", "balance": 50})

    def test_contenido_que_excede_el_tope_se_rechaza_no_se_recorta(self):
        cb, _, _, _ = make(limits={"CHATBOT_MAX_CONTENT_CHARS": 10})
        with self.assertRaises(bot.ChatError) as e:
            cb.save_bot(KEY, "Mi negocio", "x" * 11)
        self.assertEqual(e.exception.status, 400)
        self.assertEqual(cb.load_bot(KEY)["content"], "")

    def test_nombre_y_contenido_obligatorios(self):
        cb, _, _, _ = make()
        for name, content in (("", "info"), ("Mi negocio", "  "), ("n" * 81, "info")):
            with self.assertRaises(bot.ChatError):
                cb.save_bot(KEY, name, content)


class PagoPorUso(unittest.TestCase):
    def test_el_paquete_no_tiene_valor_por_defecto(self):
        for bad in (None, 0, -5, "50", True):
            with self.assertRaises(ValueError):
                bot.Chatbot(":memory:", FakeAnswerer(), lambda k: True, bad)

    def test_cada_respuesta_descuenta_una_y_sin_saldo_no_se_llama_al_modelo(self):
        cb, ans, _, _ = make(pack=2)
        bid = cb.save_bot(KEY, "N", "info")
        self.assertEqual([cb.chat(bid, "hola", ip=f"ip{i}") for i in range(3)], ["respuesta simulada"] * 2 + [bot.OUT_OF_BALANCE])
        self.assertEqual(len(ans.calls), 2)
        self.assertEqual(cb.load_bot(KEY)["balance"], 0)
        cb.save_bot(KEY, "N", "info nueva")  # volver a guardar no regala otro paquete
        self.assertEqual(cb.load_bot(KEY)["balance"], 0)

    def test_recarga_con_otra_clave_paga_una_sola_vez(self):
        cb, _, _, _ = make(valid=(KEY, KEY2), pack=2)
        bid = cb.save_bot(KEY, "N", "info")
        cb.chat(bid, "hola")
        self.assertEqual(cb.top_up(KEY, KEY2), 3)
        for args in ((KEY, KEY2), (KEY, KEY), (KEY, "TP-NO-PAGA"), (KEY, "")):
            with self.assertRaises(bot.ChatError) as e:
                cb.top_up(*args)
            self.assertEqual(e.exception.status, 400)
        with self.assertRaises(bot.ChatError) as e:
            cb.top_up("TP-NO-PAGA", KEY2)
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(cb.load_bot(KEY)["balance"], 3)
        with self.assertRaises(bot.ChatError):  # una clave gastada como recarga no abre un bot nuevo con otro paquete
            cb.save_bot(KEY2, "Otro", "info")

    def test_no_se_recarga_con_la_clave_de_otro_bot_ni_sin_bot(self):
        cb, _, _, _ = make(valid=(KEY, KEY2))
        with self.assertRaises(bot.ChatError):
            cb.top_up(KEY, KEY2)  # KEY todavía no tiene bot
        cb.save_bot(KEY, "N", "info")
        cb.save_bot(KEY2, "Otro", "info")
        with self.assertRaises(bot.ChatError):
            cb.top_up(KEY, KEY2)

    def test_consulta_sin_respuesta_no_se_cobra(self):
        for answerer in (FakeAnswerer(fail=True), FakeAnswerer(reply=None)):
            cb, _, _, _ = make(answerer=answerer, pack=5)
            bid = cb.save_bot(KEY, "N", "info")
            self.assertEqual(cb.chat(bid, "hola"), bot.UNAVAILABLE)
            self.assertEqual(cb.load_bot(KEY)["balance"], 5)

    def test_los_topes_no_descuentan_saldo(self):
        cb, _, _, _ = make(pack=5, limits={"CHATBOT_IP_HOURLY_MAX": 1})
        bid = cb.save_bot(KEY, "N", "info")
        cb.chat(bid, "hola", ip="1.1.1.1")
        self.assertEqual(cb.chat(bid, "hola", ip="1.1.1.1"), bot.OUT_OF_QUOTA)
        self.assertEqual(cb.load_bot(KEY)["balance"], 4)

    def test_la_demo_es_gratis(self):
        cb, _, _, _ = make(valid=(), pack=1)
        self.assertEqual([cb.chat("demo", "hola", ip=f"ip{i}") for i in range(3)], ["respuesta simulada"] * 3)


class Chat(unittest.TestCase):
    def test_contesta_con_la_info_del_negocio_en_el_prompt(self):
        cb, ans, _, _ = make()
        bid = cb.save_bot(KEY, "Ferretería Uno", "Cerramos los domingos.")
        self.assertEqual(cb.chat(bid, "¿abren el domingo?", ip="1.1.1.1"), "respuesta simulada")
        system, messages = ans.calls[0]
        self.assertIn("Ferretería Uno", system)
        self.assertIn("Cerramos los domingos.", system)
        self.assertEqual(messages, [{"role": "user", "content": "¿abren el domingo?"}])

    def test_bot_inexistente_y_mensaje_invalido(self):
        cb, ans, _, _ = make(limits={"CHATBOT_MAX_MESSAGE_CHARS": 5})
        bid = cb.save_bot(KEY, "N", "info")
        for args, status in ((("nope", "hola"), 404), ((bid, ""), 400), ((bid, "123456"), 400)):
            with self.assertRaises(bot.ChatError) as e:
                cb.chat(*args)
            self.assertEqual(e.exception.status, status)
        self.assertEqual(ans.calls, [])

    def test_tope_diario_corta_sin_llamar_al_modelo(self):
        cb, ans, clock, _ = make(limits={"CHATBOT_BOT_DAILY_MAX": 2, "CHATBOT_IP_HOURLY_MAX": 100})
        bid = cb.save_bot(KEY, "N", "info")
        self.assertEqual([cb.chat(bid, "hola", ip=f"ip{i}") for i in range(3)], ["respuesta simulada"] * 2 + [bot.OUT_OF_QUOTA])
        self.assertEqual(len(ans.calls), 2)
        clock.t += 86400
        self.assertEqual(cb.chat(bid, "hola", ip="ip9"), "respuesta simulada")

    def test_tope_por_ip_no_gasta_el_cupo_del_bot(self):
        cb, ans, clock, _ = make(limits={"CHATBOT_IP_HOURLY_MAX": 1})
        bid = cb.save_bot(KEY, "N", "info")
        self.assertEqual(cb.chat(bid, "hola", ip="1.1.1.1"), "respuesta simulada")
        self.assertEqual(cb.chat(bid, "hola", ip="1.1.1.1"), bot.OUT_OF_QUOTA)
        self.assertEqual(cb.chat(bid, "hola", ip="2.2.2.2"), "respuesta simulada")
        self.assertEqual(cb.usage()[0][2], 2)
        clock.t += 3601
        self.assertEqual(cb.chat(bid, "hola", ip="1.1.1.1"), "respuesta simulada")

    def test_demo_no_pide_licencia_y_tiene_tope_propio(self):
        cb, ans, _, _ = make(valid=(), limits={"CHATBOT_DEMO_DAILY_MAX": 1, "CHATBOT_IP_HOURLY_MAX": 100})
        self.assertEqual(cb.chat("demo", "hola", ip="a"), "respuesta simulada")
        self.assertIn("dato ficticio", ans.calls[0][0])
        self.assertEqual(cb.chat("demo", "hola", ip="b"), bot.OUT_OF_QUOTA)

    def test_sin_demo_configurada_no_hay_demo(self):
        cb, _, _, _ = make(demo=None)
        with self.assertRaises(bot.ChatError) as e:
            cb.chat("demo", "hola")
        self.assertEqual(e.exception.status, 404)

    def test_clave_revocada_deja_de_contestar_al_vencer_la_verificacion(self):
        cb, ans, clock, valid = make(limits={"CHATBOT_LICENSE_TTL_SECONDS": 600})
        bid = cb.save_bot(KEY, "N", "info")
        valid.clear()
        self.assertEqual(cb.chat(bid, "hola"), "respuesta simulada")  # todavía dentro de la verificación guardada
        clock.t += 601
        with self.assertRaises(bot.ChatError) as e:
            cb.chat(bid, "hola")
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(len(ans.calls), 1)

    def test_historial_se_valida_y_se_acota(self):
        cb, ans, _, _ = make(limits={"CHATBOT_MAX_HISTORY": 3})
        bid = cb.save_bot(KEY, "N", "info")
        hist = [{"role": "user", "content": "1"}, {"role": "assistant", "content": "2"},
                {"role": "user", "content": "3"}, {"role": "assistant", "content": "4"}]
        cb.chat(bid, "5", hist)
        self.assertEqual([m["content"] for m in ans.calls[0][1]], ["3", "4", "5"])  # arranca en un turno del usuario
        for bad in ([{"role": "system", "content": "x"}], [{"role": "user", "content": 3}], ["x"]):
            with self.assertRaises(bot.ChatError):
                cb.chat(bid, "hola", bad)

    def test_falla_del_modelo_no_rompe_y_cuenta_en_el_cupo(self):
        cb, _, _, _ = make(answerer=FakeAnswerer(fail=True))
        bid = cb.save_bot(KEY, "N", "info")
        self.assertEqual(cb.chat(bid, "hola"), bot.UNAVAILABLE)
        self.assertEqual(cb.usage()[0][2:], (1, 0, 0))

    def test_respuesta_vacia_o_rechazada_muestra_no_disponible(self):
        cb, _, _, _ = make(answerer=FakeAnswerer(reply=None))
        bid = cb.save_bot(KEY, "N", "info")
        self.assertEqual(cb.chat(bid, "hola"), bot.UNAVAILABLE)

    def test_no_se_guarda_el_texto_de_las_conversaciones(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.sqlite")
            cb, _, _, _ = make(db=path)
            bid = cb.save_bot(KEY, "N", "info")
            cb.chat(bid, "consulta-secreta-del-visitante", ip="9.9.9.9")
            self.assertEqual(cb.usage(), [(bid, "2023-11-14", 1, 100, 20)])
            cb.db.close()
            dump = "\n".join(sqlite3.connect(path).iterdump())
            self.assertNotIn("consulta-secreta-del-visitante", dump)
            self.assertNotIn("respuesta simulada", dump)


class ClaudeAnswererTest(unittest.TestCase):
    class _Client:
        def __init__(self, response):
            self.response, self.kwargs = response, None
            self.beta = self
            self.messages = self

        def create(self, **kwargs):
            self.kwargs = kwargs
            return self.response

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _response(self, stop_reason, content):
        O = self._Obj
        return O(stop_reason=stop_reason, content=content,
                 usage=O(input_tokens=5, cache_creation_input_tokens=None, cache_read_input_tokens=40, output_tokens=7))

    def test_arma_el_pedido_y_suma_los_tokens_cacheados(self):
        O = self._Obj
        client = self._Client(self._response("end_turn", [O(type="thinking", thinking=""), O(type="text", text=" hola ")]))
        out = bot.ClaudeAnswerer("modelo-x", client=client).answer("SISTEMA", [{"role": "user", "content": "q"}])
        self.assertEqual(out, ("hola", 45, 7))
        k = client.kwargs
        self.assertEqual(k["model"], "modelo-x")
        self.assertEqual(k["system"], [{"type": "text", "text": "SISTEMA", "cache_control": {"type": "ephemeral"}}])
        self.assertEqual(k["messages"], [{"role": "user", "content": "q"}])
        self.assertNotIn("temperature", k)

    def test_rechazo_del_modelo_devuelve_none(self):
        client = self._Client(self._response("refusal", []))
        self.assertEqual(bot.ClaudeAnswerer("m", client=client).answer("s", [])[0], None)


class Servidor(unittest.TestCase):
    def setUp(self):
        cb, self.ans, _, _ = make(demo=server.load_demo())
        self.srv = server.make_server(server.App(cb), "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def _req(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=body, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_panel_guardar_y_chatear_de_punta_a_punta(self):
        s, _, b = self._req("POST", "/api/bot", {"key": KEY, "name": "Mi negocio", "content": "Abrimos a las 9."})
        self.assertEqual(s, 200)
        bid = json.loads(b)["bot_id"]
        s, h, b = self._req("POST", "/api/chat", {"bot_id": bid, "message": "¿a qué hora abren?", "history": []})
        self.assertEqual((s, json.loads(b)), (200, {"reply": "respuesta simulada"}))
        s, _, b = self._req("POST", "/api/bot/load", {"key": KEY})
        self.assertEqual(json.loads(b)["balance"], 49)
        s, _, b = self._req("POST", "/api/bot/recarga", {"key": KEY, "new_key": "TP-NO-PAGA"})
        self.assertEqual(s, 400)
        self.assertEqual(h.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("Abrimos a las 9.", self.ans.calls[0][0])

    def test_clave_invalida_403_y_sin_cors_en_el_panel(self):
        s, h, b = self._req("POST", "/api/bot/load", {"key": "TP-MALA"})
        self.assertEqual(s, 403)
        self.assertIn("error", json.loads(b))
        self.assertNotIn("Access-Control-Allow-Origin", h)

    def test_preflight_del_chat_y_json_invalido(self):
        s, h, _ = self._req("OPTIONS", "/api/chat")
        self.assertEqual((s, h.get("Access-Control-Allow-Origin")), (204, "*"))
        req = urllib.request.Request(self.base + "/api/chat", data=b"{no es json", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 400)

    def test_paginas_estaticas_y_demo(self):
        for path, needle in (("/", b"Panel del chatbot"), ("/demo", b'data-bot="demo"'), ("/widget.js", b"/api/chat"), ("/health", b"ok")):
            s, _, b = self._req("GET", path)
            self.assertEqual(s, 200)
            self.assertIn(needle, b)
        s, _, b = self._req("POST", "/api/chat", {"bot_id": "demo", "message": "¿hacen envíos?"})
        self.assertEqual(s, 200)
        self.assertIn("NEGOCIO FICTICIO", self.ans.calls[0][0])
        self.assertEqual(self._req("GET", "/no-existe")[0], 404)


if __name__ == "__main__":
    unittest.main()
