"""Reporte diario del embudo (markdown con fecha, para commitear).

  python -m engine.report --db conversaciones.sqlite --flow ventures/<slug>/flow.yaml \
      --spend ventures/<slug>/gasto_anuncios.csv --thresholds ventures/<slug>/metricas.yaml \
      --date 2026-10-09 --out ventures/<slug>/reportes/
  python -m engine.report --synthetic     # prueba con datos sintéticos (no escribe en ningún emprendimiento)
"""
import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone

from engine.flow import load_flow
from engine.funnel import run
from engine.responder import Clock, Responder
from engine.store import Store


def synthetic(flow_path):
    """Conversaciones inventadas sobre el flow de ejemplo ficticio, con un pago simulado."""
    flow = load_flow(flow_path)
    store = Store()
    clock = Clock(start=datetime(2026, 10, 9, 12, tzinfo=timezone.utc).timestamp())
    r = Responder(flow, store, clock)
    scripts = {"+0001": ["hola", "sí", "mi consulta"], "+0002": ["hola", "no"], "+0003": ["hola"], "+0004": ["hola", "sí", "x", "sí"]}
    for phone, msgs in scripts.items():
        for m in msgs:
            r.handle_incoming(phone, m); clock.advance(seconds=30)
    return flow, store


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db"); ap.add_argument("--flow"); ap.add_argument("--spend"); ap.add_argument("--thresholds")
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--out"); ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args(argv)
    if a.synthetic:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "fixtures", "flow_ejemplo.yaml")
        flow, store = synthetic(here)
        text = run(store, flow, "2026-10-09", a.spend, a.thresholds, synthetic=True)
        print(text)
        return 0
    if not (a.db and a.flow):
        print("faltan --db y --flow (o usá --synthetic)")
        return 1
    text = run(Store(a.db), load_flow(a.flow), a.date, a.spend, a.thresholds)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, f"{a.date}.md")
        open(path, "w", encoding="utf-8").write(text)
        print(f"escrito: {path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
