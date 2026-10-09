"""Comprobación previa al lanzamiento: ¿está todo para vender?

  python -m engine.check ventures/<slug>

Revisa, sin tocar la red: config de venta, flow, anuncios, textos pendientes
(`[completar ...]`) y qué variables de entorno faltan (solo nombres, nunca valores).
Sale con código 1 si algo bloquea. Los anuncios son opcionales: sin la sección `ads` podés vender igual.
"""
import os
import sys

from engine import ads as ads_mod
from engine import payments as pm
from engine import venture as vt
from engine import whatsapp as wa
from engine.envfile import load_env


def env_report(cfg, env=None):
    env = os.environ if env is None else env
    rows = [("whatsapp", wa.missing_env(env)),
            ("mercado pago", [k for k in pm.ENV_REQUIRED if not env.get(k)])]
    if cfg.get("kind") == "download":
        rows.append(("descarga", [k for k in ("DELIVERY_SECRET",) if not env.get(k)]))
    if cfg.get("ads"):
        rows.append(("gemini", ads_mod.missing_env(ads_mod.GEMINI_ENV, env)))
        rows.append(("meta ads", ads_mod.missing_env(ads_mod.META_ENV, env)))
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 1
    load_env()
    d = argv[0]
    if not os.path.exists(os.path.join(d, "venture.yaml")):
        print(f"no hay venture.yaml en {d}. Armalo con: python -m engine.scaffold <id> --source <ingredients.json>")
        return 1
    res = vt.validate_all(d)
    cfg = vt.load(d)
    blocking = 0
    for sec, label in (("venta", "venta y entrega"), ("flow", "flow de whatsapp"), ("anuncios", "anuncios"), ("pendientes", "textos por completar")):
        errs = res[sec]
        optional = sec == "anuncios" and not cfg.get("ads")
        print(f"{'·' if optional else ('✗' if errs else '✓')} {label}")
        for e in errs:
            print(f"    - {e}")
        if errs and not optional:
            blocking += len(errs)
    print("variables de entorno:")
    for label, miss in env_report(cfg):
        print(f"  {'✗' if miss else '✓'} {label}" + (": faltan " + ", ".join(miss) if miss else ""))
        blocking += len(miss)
    print("\n" + ("LISTO para arrancar." if not blocking else f"faltan {blocking} cosas antes de arrancar."))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
