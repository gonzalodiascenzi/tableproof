"""Arma un emprendimiento nuevo a partir de un ingrediente de seedproof.

  python -m engine.scaffold <id> --source <data/ingredients.json | URL> [--kind access|download] [--slug nombre]

Copia ventures/_plantilla a ventures/<slug>/, deja el nombre del ingrediente y guarda
`ingrediente.json` (con sus fuentes) al lado. Nada de lo que define el dueño (precio, presupuesto,
países, textos) se completa solo: queda como `[completar ...]` hasta que lo escribas.
El archivo de seedproof se genera en `data/ingredients.json` de ese repo (scripts/export_ingredients.py).
"""
import argparse
import json
import os
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME_PLACEHOLDER = "[completar: nombre del emprendimiento]"


def read_source(source):
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=20) as r:
            return json.loads(r.read().decode())
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def scaffold(ingredient_id, source, kind="access", slug=None, root=ROOT):
    data = read_source(source)
    ing = next((i for i in data.get("ingredients", []) if i.get("id") == ingredient_id), None)
    if not ing:
        raise ValueError(f"no hay un ingrediente '{ingredient_id}' en {source}")
    if kind not in ("access", "download"):
        raise ValueError("kind debe ser access o download")
    slug = slug or ingredient_id
    if os.sep in slug or slug.startswith((".", "_")):
        raise ValueError("slug inválido")
    dest = os.path.join(root, "ventures", slug)
    if os.path.exists(dest):
        raise ValueError(f"ya existe ventures/{slug}")
    tpl = os.path.join(root, "ventures", "_plantilla")
    os.makedirs(dest)
    shutil.copy(os.path.join(tpl, "flow.yaml"), os.path.join(dest, "flow.yaml"))
    text = open(os.path.join(tpl, f"venture.{kind}.yaml"), encoding="utf-8").read()
    text = text.replace(NAME_PLACEHOLDER, ing["name"]).replace("origen_seedproof: null", f"origen_seedproof: {ingredient_id}")
    with open(os.path.join(dest, "venture.yaml"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(dest, "ingrediente.json"), "w", encoding="utf-8") as f:
        json.dump(ing, f, ensure_ascii=False, indent=2)
    if kind == "download":
        os.makedirs(os.path.join(dest, "entrega"))
        open(os.path.join(dest, "entrega", ".gitkeep"), "w").close()
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ingredient_id")
    ap.add_argument("--source", required=True)
    ap.add_argument("--kind", default="access")
    ap.add_argument("--slug")
    a = ap.parse_args(argv)
    try:
        dest = scaffold(a.ingredient_id, a.source, a.kind, a.slug)
    except (ValueError, OSError) as e:
        print(f"error: {e}")
        return 1
    print(f"creado {os.path.relpath(dest, ROOT)}. Completá venture.yaml y flow.yaml y corré: python -m engine.check {os.path.relpath(dest, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
