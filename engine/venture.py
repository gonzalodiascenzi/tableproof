"""Config de un emprendimiento: `ventures/<slug>/venture.yaml` + `flow.yaml`.

Lo que define el dueño y NO tiene valor por defecto: `price_ars` y, para anuncios,
`ads.daily_budget` y `ads.countries` (regla de CLAUDE.md). Cualquier valor que
todavía diga `[completar ...]` hace fallar la comprobación: la plantilla no se
puede lanzar a medio llenar.

Tipos de producto (`kind`):
  access    -> clave de licencia por whatsapp + `access_url`
  download  -> link firmado a `entrega/<file>` (el archivo no se commitea)
"""
import os

import yaml

from engine import ads as ads_mod
from engine import checkout as ck
from engine import payments as pm
from engine.flow import load_flow, validate_flow

PLACEHOLDER = "[completar"
KINDS = ("access", "download")


def load(venture_dir):
    with open(os.path.join(venture_dir, "venture.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_placeholders(obj, path=""):
    """Rutas de todos los textos que todavía dicen `[completar ...]`."""
    out = []
    if isinstance(obj, str):
        if PLACEHOLDER in obj:
            out.append(path or "(raíz)")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += find_placeholders(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += find_placeholders(v, f"{path}[{i}]")
    return out


def _fmt_ok(template, **vals):
    try:
        template.format(**vals)
        return True
    except (KeyError, IndexError, ValueError):
        return False


def validate_sale(cfg, venture_dir):
    errs = []
    if not str(cfg.get("name") or "").strip():
        errs.append("falta 'name'")
    kind = cfg.get("kind")
    if kind not in KINDS:
        errs.append(f"'kind' debe ser uno de {KINDS}")
    try:
        pm.load_venture_config(cfg)
    except pm.ConfigError as e:
        errs.append(str(e))
    for k in ("public_base_url", "delivery_message", "already_paid_message", "checkout_failed_message"):
        if not str(cfg.get(k) or "").strip():
            errs.append(f"falta '{k}'")
    if cfg.get("public_base_url") and not str(cfg["public_base_url"]).startswith("https://"):
        errs.append("public_base_url debe ser https")
    dm = str(cfg.get("delivery_message") or "")
    if kind == "access":
        if not str(cfg.get("access_url") or "").startswith("https://"):
            errs.append("access_url debe ser una URL https")
        if dm and (not _fmt_ok(dm, key="K", url="U") or "{key}" not in dm):
            errs.append("delivery_message debe incluir {key} y no usar otras llaves { }")
    elif kind == "download":
        f = str(cfg.get("file") or "")
        if not f or os.sep in f or f.startswith("."):
            errs.append("'file' debe ser el nombre de un archivo dentro de entrega/")
        elif not os.path.exists(os.path.join(venture_dir, "entrega", f)):
            errs.append(f"no está el archivo entrega/{f} (se pone a mano; no se commitea)")
        if dm and (not _fmt_ok(dm, url="U") or "{url}" not in dm):
            errs.append("delivery_message debe incluir {url} y no usar otras llaves { }")
    return errs


def validate_flow_file(venture_dir):
    path = os.path.join(venture_dir, "flow.yaml")
    if not os.path.exists(path):
        return ["falta flow.yaml"]
    flow = load_flow(path)
    errs = validate_flow(flow)
    if not errs and not any(ck.PAY_TOKEN in str(s.get("message", "")) for s in flow["states"].values()):
        errs.append(f"ningún mensaje del flow incluye {ck.PAY_TOKEN}: no hay dónde poner el link de pago")
    return errs


def validate_ads(cfg):
    ads = cfg.get("ads")
    if not ads:
        return ["no hay sección 'ads' (opcional: sin anuncios podés vender igual)"]
    errs = []
    num = str(ads.get("whatsapp_number") or "")
    if not (num.isdigit() and 8 <= len(num) <= 15):
        errs.append("ads.whatsapp_number: solo dígitos con código de país, sin +")
    countries = ads.get("countries")
    if not (isinstance(countries, list) and countries and all(isinstance(c, str) and len(c) == 2 for c in countries)):
        errs.append("ads.countries: lo define el dueño, lista de códigos de 2 letras (por ejemplo [AR])")
    b = ads.get("daily_budget")
    if isinstance(b, bool) or not isinstance(b, (int, float)) or b <= 0:
        errs.append("ads.daily_budget: lo define el dueño; no hay presupuesto por defecto")
    variants = ads.get("variants")
    if not (isinstance(variants, list) and variants):
        errs.append("ads.variants: al menos una variante")
        return errs
    for i, v in enumerate(variants, start=1):
        for k in ("headline", "primary_text", "image_prompt"):
            if not str((v or {}).get(k) or "").strip():
                errs.append(f"ads.variants[{i}]: falta '{k}'")
    errs += ["promesa que no se publica en " + m for m in ads_mod.guard_copy(cfg)]
    return errs


def validate_all(venture_dir):
    """-> {sección: [errores]} (vacío = todo bien). Secciones: venta, flow, anuncios, pendientes."""
    cfg = load(venture_dir)
    out = {"venta": validate_sale(cfg, venture_dir), "flow": validate_flow_file(venture_dir), "anuncios": validate_ads(cfg)}
    flow_path = os.path.join(venture_dir, "flow.yaml")
    ph = find_placeholders(cfg)
    if os.path.exists(flow_path):
        ph += ["flow." + p for p in find_placeholders(load_flow(flow_path))]
    out["pendientes"] = [f"completar: {p}" for p in ph]
    return out
