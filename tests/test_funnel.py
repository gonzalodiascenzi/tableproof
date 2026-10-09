import copy
import os
import tempfile
import unittest
from datetime import datetime, timezone

from engine import funnel
from engine import payments as pm
from engine.flow import load_flow
from engine.report import synthetic
from engine.responder import Clock, Responder
from engine.store import Store
from tests.test_engine import FIX

DATE = "2026-10-09"


def world(flow=None, scripts=None):
    flow = flow or load_flow(FIX)
    store = Store()
    clock = Clock(start=datetime(2026, 10, 9, 12, tzinfo=timezone.utc).timestamp())
    r = Responder(flow, store, clock)
    for phone, msgs in (scripts or {}).items():
        for m in msgs:
            r.handle_incoming(phone, m); clock.advance(seconds=10)
    return flow, store, clock


def write(d, name, text):
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8").write(text)
    return p


class CountTests(unittest.TestCase):
    def test_conversation_counts_only_after_second_message(self):
        flow, store, _ = world(scripts={"a": ["hola"], "b": ["hola", "sí"], "c": ["hola", "no"]})
        m = funnel.compute(store, flow, DATE, None)
        self.assertEqual(m["conversaciones"], 2)

    def test_used_free_is_reaching_a_free_value_state(self):
        flow, store, _ = world(scripts={"b": ["hola", "sí"], "c": ["hola", "no"]})
        m = funnel.compute(store, flow, DATE, None)
        self.assertEqual((m["conversaciones"], m["usaron_gratis"]), (2, 1))

    def test_paid_counts_only_users_of_free_value_with_approved_order(self):
        flow, store, clock = world(scripts={"b": ["hola", "sí"], "c": ["hola", "no"]})
        orders = pm.Orders(store, pm.load_venture_config({"price_ars": 1, "item_title": "x", "notification_url": "https://x.invalid", "delivery_failed_message": "x"}), clock=clock.now)
        orders.create("b", "o1"); orders.update("o1", status="pagado", paid_at=clock.now())
        orders.create("c", "o2"); orders.update("o2", status="pendiente")
        m = funnel.compute(store, flow, DATE, None)
        self.assertEqual((m["pagaron"], m["pagaron_total"]), (1, 1))

    def test_events_after_the_report_date_do_not_count(self):
        flow, store, _ = world(scripts={"b": ["hola", "sí"]})
        self.assertEqual(funnel.compute(store, flow, "2026-10-08", None)["conversaciones"], 0)

    def test_flow_without_free_step_does_not_invent_the_metric(self):
        flow = copy.deepcopy(load_flow(FIX))
        for st in flow["states"].values():
            st.pop("free_value", None)
        flow, store, _ = world(flow, {"b": ["hola", "sí"]})
        text = funnel.run(store, flow, DATE)
        self.assertIn("no tiene paso gratis: decidí qué métrica va en su lugar", text)
        self.assertEqual(funnel.metric_values(funnel.compute(store, flow, DATE, None))["pct_usa_gratis"], None)


class SpendTests(unittest.TestCase):
    def test_no_spend_means_sin_dato_not_estimate(self):
        flow, store, _ = world(scripts={"b": ["hola", "sí"]})
        self.assertIn("sin dato (gasto en anuncios sin cargar)", funnel.run(store, flow, DATE))

    def test_spend_from_csv_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "g.csv", "fecha,monto_ars\n2026-10-08,100\n2026-10-09,50.5\n2026-10-10,999\nmala,x\n2026-10-09,-3\n")
            total, rows, errs = funnel.read_spend(p, DATE)
            self.assertEqual((total, rows, len(errs)), (150.5, 2, 2))   # el gasto futuro y las filas malas no cuentan
            flow, store, _ = world(scripts={"b": ["hola", "sí"]})
            self.assertIn("ARS 150.50 (gasto ARS 150.50 / 1)", funnel.run(store, flow, DATE, spend_csv=p))


class ThresholdTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.scripts = {f"u{i}": ["hola", "sí"] for i in range(4)}

    def test_empty_thresholds_say_undefined_and_never_recommend(self):
        p = write(self.d, "m.yaml", "muestra_minima:\nmatar_si: []\ncorregir_si: []\nescalar_si: []\n")
        flow, store, _ = world(scripts=self.scripts)
        text = funnel.run(store, flow, DATE, thresholds=p)
        self.assertIn("Umbrales sin definir", text)
        self.assertNotIn("se cumple un criterio", text)

    def test_small_sample_shows_counts_not_firm_percentages(self):
        p = write(self.d, "m.yaml", "muestra_minima: 100\nmatar_si: [{metrica: pct_usa_gratis, op: '<', valor: 90}]\n")
        flow, store, _ = world(scripts=self.scripts)
        text = funnel.run(store, flow, DATE, thresholds=p)
        self.assertIn("No alcanza para concluir", text)
        self.assertIn("| 4 de 4 |", text)
        self.assertNotIn("%)", text)
        self.assertIn("no se evalúa ninguno", text)    # con muestra chica no se evalúan umbrales

    def test_undefined_minimum_sample_blocks_percentages_and_rules(self):
        p = write(self.d, "m.yaml", "matar_si: [{metrica: pct_usa_gratis, op: '<', valor: 90}]\n")
        flow, store, _ = world(scripts=self.scripts)
        text = funnel.run(store, flow, DATE, thresholds=p)
        self.assertIn("Muestra mínima sin definir", text)
        self.assertNotIn("se cumple un criterio", text)

    def test_rule_is_reported_when_sample_is_enough_and_decision_stays_with_owner(self):
        p = write(self.d, "m.yaml", "muestra_minima: 3\nmatar_si: [{metrica: pct_paga, op: '<', valor: 10}]\nescalar_si: [{metrica: pct_usa_gratis, op: '>=', valor: 90}]\n")
        flow, store, _ = world(scripts=self.scripts)
        text = funnel.run(store, flow, DATE, thresholds=p)
        self.assertIn("se cumple un criterio de corte: pct_paga < 10", text)
        self.assertIn("se cumple un criterio de escala: pct_usa_gratis >= 90", text)
        self.assertIn("La decisión es del dueño", text)
        self.assertIn("(100%)", text)


class SyntheticTests(unittest.TestCase):
    def test_synthetic_report_is_labeled_and_has_the_three_numbers(self):
        flow, store = synthetic(FIX)
        text = funnel.run(store, flow, "2026-10-09", synthetic=True)
        self.assertIn("DATOS SINTÉTICOS", text)
        for label in ("costo por conversación iniciada", "% que usa el valor gratis", "% que paga"):
            self.assertIn(label, text)
        self.assertIn("Umbrales sin definir", text)

    def test_templates_ship_with_empty_thresholds(self):
        import yaml
        cfg = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "framework", "metricas.plantilla.yaml")))
        self.assertIsNone(cfg["muestra_minima"])
        self.assertEqual((cfg["matar_si"], cfg["corregir_si"], cfg["escalar_si"]), ([], [], []))


if __name__ == "__main__":
    unittest.main()
