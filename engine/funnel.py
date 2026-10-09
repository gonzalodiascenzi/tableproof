"""Embudo y reporte diario con los tres números de la sección 6 de framework-emprendimiento.md.

  1. costo por conversación iniciada = gasto en anuncios / conversaciones
  2. % que usa el valor gratis       = usaron gratis / conversaciones
  3. % que paga                      = pagaron / usaron gratis

Reglas:
- una conversación cuenta cuando la persona contesta la primera pregunta del
  respondedor (es decir, manda al menos un segundo mensaje);
- "usó el valor gratis" = llegó a un estado del flow marcado `free_value: true`.
  Si el flow no tiene ninguno, el emprendimiento no tiene paso gratis: el
  reporte NO inventa la métrica y pregunta cuál la reemplaza;
- el gasto en anuncios se carga a mano en un csv (fecha,monto_ars). Si no hay
  filas, el costo por conversación es "sin dato": no se estima;
- los umbrales de corte y escala los completa el dueño en metricas.yaml. Si
  están vacíos el reporte dice "umbrales sin definir" y no emite ninguna
  recomendación; tampoco compara nada si el tamaño mínimo de muestra
  (`muestra_minima`) no está definido o no se alcanza;
- con muestras chicas se muestran cuentas (x de n), nunca un porcentaje solo.
"""
import csv
import operator
import os
from datetime import datetime, timedelta, timezone

import yaml

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
METRICS = ("costo_por_conversacion", "pct_usa_gratis", "pct_paga")


def _day_end(date):
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    return d.timestamp()


def free_states(flow):
    return {n for n, st in flow["states"].items() if isinstance(st, dict) and st.get("free_value")}


def read_spend(path, until_date):
    """Suma el gasto cargado a mano hasta la fecha. -> (total o None, filas, errores)."""
    if not path or not os.path.exists(path):
        return None, 0, []
    total, rows, errs = 0.0, 0, []
    with open(path, newline="", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            try:
                d = datetime.strptime(r["fecha"].strip(), "%Y-%m-%d").date()
                amount = float(r["monto_ars"])
                if amount < 0:
                    raise ValueError
            except (KeyError, ValueError, AttributeError):
                errs.append(f"fila {i} inválida")
                continue
            if d.isoformat() <= until_date:
                total += amount
                rows += 1
    return (total if rows else None), rows, errs


def compute(store, flow, date, spend_total):
    end = _day_end(date)
    db = store.db
    ev = lambda sql, *a: db.execute(sql, a).fetchall()
    started = {r[0] for r in ev("SELECT phone FROM events WHERE direction='in' AND ts < ? GROUP BY phone HAVING COUNT(*) >= 2", end)}
    fs = free_states(flow)
    used = set()
    if fs:
        q = "SELECT DISTINCT phone FROM events WHERE direction='estado' AND ts < ? AND text IN (%s)" % ",".join("?" * len(fs))
        used = {r[0] for r in ev(q, end, *fs)} & started
    paid = set()
    try:
        paid = {r[0] for r in ev("SELECT phone FROM orders WHERE status IN ('pagado','entregado','entrega_fallida') AND paid_at < ?", end)}
    except Exception:
        pass  # todavía no existe la tabla de pedidos
    day_start = end - 86400
    new_today = len({r[0] for r in ev("SELECT phone FROM events WHERE direction='in' AND ts >= ? AND ts < ? GROUP BY phone HAVING COUNT(*) >= 1", day_start, end)} & started)
    return {"conversaciones": len(started), "nuevas_hoy": new_today, "tiene_paso_gratis": bool(fs),
            "usaron_gratis": len(used), "pagaron": len(paid & used) if fs else None,
            "pagaron_total": len(paid), "gasto_total": spend_total}


def load_thresholds(path):
    cfg = yaml.safe_load(open(path, encoding="utf-8")) if path and os.path.exists(path) else None
    cfg = cfg or {}
    rules = {k: cfg.get(k) or [] for k in ("matar_si", "corregir_si", "escalar_si")}
    return cfg.get("muestra_minima"), rules


def metric_values(m):
    v = {}
    v["costo_por_conversacion"] = (m["gasto_total"] / m["conversaciones"]) if (m["gasto_total"] is not None and m["conversaciones"]) else None
    v["pct_usa_gratis"] = (100 * m["usaron_gratis"] / m["conversaciones"]) if (m["tiene_paso_gratis"] and m["conversaciones"]) else None
    v["pct_paga"] = (100 * m["pagaron"] / m["usaron_gratis"]) if (m["tiene_paso_gratis"] and m["usaron_gratis"]) else None
    return v


def evaluate_rules(values, rules):
    hits = {}
    for name, lst in rules.items():
        for r in lst:
            val = values.get(r.get("metrica"))
            if val is not None and r.get("op") in OPS and OPS[r["op"]](val, r["valor"]):
                hits.setdefault(name, []).append(f"{r['metrica']} {r['op']} {r['valor']} (valor actual {val:.1f})")
    return hits


def render_report(date, m, min_sample, rules, spend_rows, spend_errs, synthetic=False):
    v = metric_values(m)
    L = [f"# Reporte del embudo — {date}", ""]
    if synthetic:
        L += ["> **DATOS SINTÉTICOS**: generados para probar el reporte. No son de ningún emprendimiento.", ""]
    L += [f"Conversaciones (contestaron la primera pregunta): **{m['conversaciones']}** (nuevas hoy: {m['nuevas_hoy']}).", ""]
    enough = min_sample is not None and m["conversaciones"] >= min_sample
    if min_sample is None:
        L += ["**Muestra mínima sin definir** (`muestra_minima` en metricas.yaml): ningún número de abajo se debe tomar como firme.", ""]
    elif not enough:
        L += [f"**No alcanza para concluir**: hay {m['conversaciones']} conversaciones y el mínimo definido es {min_sample}.", ""]
    L += ["| métrica | cómo se mide | valor |", "|---|---|---|"]
    cpc = "sin dato (gasto en anuncios sin cargar)" if v["costo_por_conversacion"] is None and m["gasto_total"] is None else (
        "sin dato (todavía no hay conversaciones)" if v["costo_por_conversacion"] is None else
        f"ARS {v['costo_por_conversacion']:.2f} (gasto ARS {m['gasto_total']:.2f} / {m['conversaciones']})")
    L.append(f"| costo por conversación iniciada | gasto en anuncios / conversaciones | {cpc} |")
    if not m["tiene_paso_gratis"]:
        L.append("| % que usa el valor gratis | usaron gratis / conversaciones | **este emprendimiento no tiene paso gratis: decidí qué métrica va en su lugar** |")
        L.append(f"| % que paga | pagaron / usaron gratis | sin dato (sin paso gratis). Pagaron en total: {m['pagaron_total']} de {m['conversaciones']} conversaciones |")
    else:
        L.append(f"| % que usa el valor gratis | usaron gratis / conversaciones | {m['usaron_gratis']} de {m['conversaciones']}" + (f" ({v['pct_usa_gratis']:.0f}%)" if enough and v["pct_usa_gratis"] is not None else "") + " |")
        L.append(f"| % que paga | pagaron / usaron gratis | {m['pagaron']} de {m['usaron_gratis']}" + (f" ({v['pct_paga']:.0f}%)" if enough and v["pct_paga"] is not None else "") + " |")
    L += ["", f"Gasto cargado a mano: {spend_rows} fila(s)." + (" Filas inválidas: " + "; ".join(spend_errs) if spend_errs else ""), ""]
    L += ["## Criterio de corte y de escala", ""]
    any_rule = any(rules.values())
    if not any_rule:
        L += ["**Umbrales sin definir.** Los completa el dueño en `metricas.yaml` antes de gastar. Este reporte no emite ninguna recomendación de matar, corregir o escalar.", ""]
    elif not enough:
        L += ["Hay umbrales definidos, pero la muestra no alcanza (o su mínimo no está definido): no se evalúa ninguno.", ""]
    else:
        hits = evaluate_rules(v, rules)
        labels = {"matar_si": "se cumple un criterio de corte", "corregir_si": "se cumple un criterio de corrección", "escalar_si": "se cumple un criterio de escala"}
        if not hits:
            L += ["Ningún umbral definido se cumple hoy."]
        for k, items in hits.items():
            L += [f"- {labels[k]}: " + "; ".join(items)]
        L += ["", "La decisión es del dueño; el reporte solo muestra qué regla se cumple."]
    return "\n".join(L) + "\n"


def run(store, flow, date, spend_csv=None, thresholds=None, synthetic=False):
    total, rows, errs = read_spend(spend_csv, date)
    m = compute(store, flow, date, total)
    min_sample, rules = load_thresholds(thresholds)
    return render_report(date, m, min_sample, rules, rows, errs, synthetic)
