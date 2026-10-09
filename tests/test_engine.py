import copy
import os
import tempfile
import unittest

from engine.flow import load_flow, validate_flow
from engine.responder import Clock, Responder
from engine.store import Store

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "flow_ejemplo.yaml")
P = "+000-test"


def make(db=":memory:"):
    flow = load_flow(FIX)
    return Responder(flow, Store(db), Clock()), flow


class ValidatorTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        self.assertEqual(validate_flow(load_flow(FIX)), [])

    def test_state_without_human_exit_fails(self):
        f = load_flow(FIX)
        del f["states"]["gratis"]["human_exit"]
        self.assertTrue(any("sin salida a humano" in e and "gratis" in e for e in validate_flow(f)))

    def test_orphan_transition_fails(self):
        f = load_flow(FIX)
        f["states"]["oferta"]["transitions"].append({"match": ["quizas"], "to": "no_existe"})
        self.assertTrue(any("huérfana" in e for e in validate_flow(f)))

    def test_unreachable_state_fails(self):
        f = load_flow(FIX)
        f["states"]["isla"] = {"message": "x", "human_exit": True, "transitions": [{"default": True, "to": "fin"}]}
        self.assertTrue(any("inalcanzable" in e and "isla" in e for e in validate_flow(f)))

    def test_unquoted_yaml_boolean_keyword_is_rejected(self):
        import yaml
        f = yaml.safe_load(open(FIX).read().replace('["no"]', '[no]'))
        self.assertTrue(any("no es texto" in e for e in validate_flow(f)))

    def test_missing_disclosure_or_global_exit_fails(self):
        f = load_flow(FIX); f["disclosure"] = " "
        self.assertTrue(any("disclosure" in e for e in validate_flow(f)))
        f = load_flow(FIX); del f["human_exit"]
        self.assertTrue(any("human_exit" in e for e in validate_flow(f)))


class HumanExitTests(unittest.TestCase):
    def test_human_exit_works_in_every_non_terminal_state(self):
        _, flow = make()
        for name, st in flow["states"].items():
            if st.get("terminal"):
                continue
            r, flow = make()
            # llevar la conversación hasta `name`
            path = {"saludo": [], "gratis": ["sí"], "oferta": ["sí", "mi consulta"]}[name]
            r.handle_incoming(P, "hola")
            for m in path:
                r.handle_incoming(P, m)
            self.assertEqual(r.store.contact(P)["state"], name)
            out = r.handle_incoming(P, "quiero hablar con una persona")
            self.assertEqual(out, [flow["human_exit"]["message"]], name)
            self.assertEqual(r.store.contact(P)["human"], 1)
            self.assertEqual(r.handle_incoming(P, "sí"), [])  # el bot calla mientras hay humano

    def test_release_human_resumes_bot(self):
        r, _ = make()
        r.handle_incoming(P, "hola"); r.handle_incoming(P, "persona")
        r.release_human(P)
        self.assertTrue(r.handle_incoming(P, "sí"))


class FirstMessageAndOptInTests(unittest.TestCase):
    def test_first_message_discloses_automatic_assistant_with_a_person(self):
        r, flow = make()
        out = r.handle_incoming(P, "hola")
        self.assertTrue(out[0].startswith(flow["disclosure"].strip()))
        self.assertIn("asistente automático", out[0])
        self.assertIn("persona", out[0])

    def test_opt_in_is_recorded_with_date(self):
        r, _ = make()
        r.clock.advance(seconds=5)
        r.handle_incoming(P, "hola")
        c = r.store.contact(P)
        self.assertEqual(c["opt_in_at"], r.clock.now())
        self.assertEqual(c["opt_in_source"], "mensaje_entrante")
        r.record_opt_in(P)
        self.assertEqual(r.store.contact(P)["opt_in_source"], "explicito")


class StopTests(unittest.TestCase):
    def test_baja_cuts_immediately_and_records_date(self):
        r, flow = make()
        r.handle_incoming(P, "hola")
        out = r.handle_incoming(P, "BAJA")
        self.assertEqual(out, [flow["stop"]["message"]])
        self.assertIsNotNone(r.store.contact(P)["opt_out_at"])
        self.assertEqual(r.handle_incoming(P, "sí"), [])
        self.assertEqual(r.follow_up(P, free_text="hola de nuevo"), [])
        r.clock.advance(hours=48)
        r.record_opt_in(P)  # solo un opt-in explícito nuevo reactiva
        self.assertIsNone(r.store.contact(P)["opt_out_at"])

    def test_stop_in_first_message_and_stop_word_inside_sentence(self):
        r, flow = make()
        self.assertEqual(r.handle_incoming(P, "stop"), [flow["stop"]["message"]])
        r2, _ = make()
        r2.handle_incoming(P, "hola")
        self.assertEqual(r2.handle_incoming(P, "por favor, baja"), [flow["stop"]["message"]])

    def test_stop_is_checked_before_human_exit(self):
        r, flow = make()
        r.handle_incoming(P, "hola")
        self.assertEqual(r.handle_incoming(P, "baja, no quiero hablar con una persona"), [flow["stop"]["message"]])


class WindowTests(unittest.TestCase):
    def test_free_text_only_inside_24h(self):
        r, _ = make()
        r.handle_incoming(P, "hola")
        r.clock.advance(hours=23)
        self.assertEqual(r.follow_up(P, free_text="seguimiento libre"), ["seguimiento libre"])
        r.clock.advance(hours=2)  # 25 h desde el último mensaje del cliente
        self.assertEqual(r.follow_up(P, free_text="seguimiento libre"), [])
        self.assertEqual(r.store.events(P)[-1]["note"], "ventana_vencida")

    def test_expired_window_allows_only_approved_template_with_explicit_opt_in(self):
        r, flow = make()
        r.handle_incoming(P, "hola")
        r.clock.advance(hours=30)
        self.assertEqual(r.follow_up(P, template="seguimiento_24h"), [])  # opt-in solo por mensaje entrante
        r.record_opt_in(P)
        self.assertEqual(r.follow_up(P, template="seguimiento_24h"), [flow["templates"]["seguimiento_24h"]])
        self.assertEqual(r.follow_up(P, template="no_aprobada"), [])
        self.assertEqual(r.follow_up(P, free_text="texto libre"), [])

    def test_customer_message_reopens_window(self):
        r, _ = make()
        r.handle_incoming(P, "hola")
        r.clock.advance(hours=30)
        self.assertFalse(r.window_open(P))
        self.assertTrue(r.handle_incoming(P, "sí"))
        self.assertTrue(r.window_open(P))


class OutOfOrderTests(unittest.TestCase):
    def test_unmatched_reply_reprompts_without_moving(self):
        r, flow = make()
        r.handle_incoming(P, "hola")
        out = r.handle_incoming(P, "blablabla")
        self.assertEqual(out, [flow["states"]["saludo"]["reprompt"]])
        self.assertEqual(r.store.contact(P)["state"], "saludo")

    def test_answer_to_a_later_state_does_not_skip_ahead(self):
        r, _ = make()
        r.handle_incoming(P, "hola")
        r.handle_incoming(P, "no")  # 'no' va a despedida
        self.assertEqual(r.store.contact(P)["state"], "despedida")

    def test_late_arriving_message_does_not_move_state(self):
        r, _ = make()
        t0 = r.clock.now()
        r.handle_incoming(P, "hola", ts=t0)
        r.handle_incoming(P, "sí", ts=t0 + 60)       # -> gratis
        self.assertEqual(r.handle_incoming(P, "no", ts=t0 + 30), [])  # llega tarde
        self.assertEqual(r.store.contact(P)["state"], "gratis")
        self.assertEqual(r.store.events(P)[-1]["note"], "desordenado")

    def test_message_in_terminal_state_does_not_crash(self):
        r, _ = make()
        r.handle_incoming(P, "hola"); r.handle_incoming(P, "no")
        r.handle_incoming(P, "cualquier cosa")


class PersistenceTests(unittest.TestCase):
    def test_state_survives_reopening_the_database(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "c.sqlite")
            r, _ = make(db)
            r.handle_incoming(P, "hola"); r.handle_incoming(P, "sí")
            r.store.close()
            r2, _ = make(db)
            self.assertEqual(r2.store.contact(P)["state"], "gratis")
            self.assertTrue(r2.handle_incoming(P, "mi consulta"))


if __name__ == "__main__":
    unittest.main()
