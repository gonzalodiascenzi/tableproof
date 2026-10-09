"""Anuncios: imágenes con Gemini y campaña de click-to-whatsapp en Meta Ads.

  python -m engine.ads plan    ventures/<slug>   # arma los pedidos y los imprime; sin red ni claves
  python -m engine.ads images  ventures/<slug>   # genera las imágenes con Gemini (no pisa las existentes)
  python -m engine.ads create  ventures/<slug>   # crea campaña, conjunto, creatividades y anuncios, SIEMPRE en PAUSA
  python -m engine.ads activate ventures/<slug> --confirmo-gasto   # recién acá se enciende y empieza a gastar

Reglas:
- el presupuesto diario y los países los pone el dueño (ads.daily_budget, ads.countries en venture.yaml); no hay valor por defecto.
- todo se crea en PAUSA; encender es un paso aparte con una bandera explícita.
- el texto de los anuncios pasa por una guarda de promesas (ingresos garantizados, "sin riesgo", etc.): si salta, no se crea nada.
- las imágenes se piden SIN texto, logos ni marcas de terceros: el titular va en el anuncio, no en la imagen.
- secretos solo por variables de entorno; nunca se loguean (los errores traen solo el mensaje de la API).

[hipótesis] (ver docs/ads-verificado.md): el modelo y la forma exacta del pedido de Gemini, la
versión de la Marketing API, los campos de click-to-whatsapp y que daily_budget vaya en la
unidad mínima de la moneda de la cuenta (centavos). Todo sale PAUSADO justamente para que lo
revises en el Administrador de anuncios antes de encender nada.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

GEMINI_BASE = "https://generativelanguage.googleapis.com"
IMAGE_RULES = ("Imagen publicitaria limpia, sin texto, sin letras, sin logos ni marcas de terceros y sin personas reales "
               "identificables. Estilo: ")

RISKY = [
    "garantizado", "garantizada", "garantizamos", "ganá plata", "gana plata", "ganar dinero", "ganar plata",
    "ingresos asegurados", "ingreso asegurado", "dinero fácil", "dinero facil", "plata fácil", "plata facil",
    "sin riesgo", "100% seguro", "hacete rico", "hazte rico", "millonario", "resultados asegurados",
    "plata automática garantizada", "te vas a enriquecer",
]
GEMINI_ENV = ("GEMINI_API_KEY", "GEMINI_IMAGE_MODEL")
META_ENV = ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID", "META_API_VERSION")


class AdsError(RuntimeError):
    pass


def copy_problems(text, extra=()):
    """Frases de promesa que no se publican. -> lista de las que aparecen."""
    t = " ".join(str(text or "").lower().split())
    return [p for p in list(RISKY) + [str(x).lower() for x in extra] if p and p in t]


def missing_env(names, env=None):
    env = os.environ if env is None else env
    return [k for k in names if not env.get(k)]


def _http(method, url, headers, body):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            err = json.loads(e.read().decode())
            err = err.get("error", err)
            detail = (err.get("message") if isinstance(err, dict) else str(err)) or ""
        except Exception:
            pass
        raise AdsError(f"HTTP {e.code}: {detail[:300]}") from None  # solo el mensaje: nunca el token


# ---- Gemini -------------------------------------------------------------
class GeminiImages:
    """api=`generate_content` (por defecto) o `interactions` (la que describe la página de imágenes de Gemini, leída el 2026-10-09)."""

    def __init__(self, api_key, model, api="generate_content", request=None):
        if not (api_key and model):
            raise AdsError("faltan GEMINI_API_KEY o GEMINI_IMAGE_MODEL")
        if api not in ("generate_content", "interactions"):
            raise AdsError("GEMINI_IMAGE_API debe ser generate_content o interactions")
        self._key, self.model, self.api, self._request = api_key, model, api, request or _http

    @classmethod
    def from_env(cls, env=None, request=None):
        env = os.environ if env is None else env
        miss = missing_env(GEMINI_ENV, env)
        if miss:
            raise AdsError("faltan variables de entorno: " + ", ".join(miss))
        return cls(env["GEMINI_API_KEY"], env["GEMINI_IMAGE_MODEL"], env.get("GEMINI_IMAGE_API") or "generate_content", request)

    def __repr__(self):
        return f"GeminiImages(model={self.model!r}, api={self.api!r})"

    def generate(self, prompt, aspect_ratio="1:1"):
        """-> (bytes, mime). `prompt` es la descripción visual; las reglas de imagen se anteponen."""
        text = IMAGE_RULES + prompt
        headers = {"x-goog-api-key": self._key, "Content-Type": "application/json"}
        if self.api == "interactions":
            body = {"model": self.model, "input": text,
                    "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": aspect_ratio}}
            resp = self._request("POST", f"{GEMINI_BASE}/v1beta/interactions", headers, json.dumps(body).encode())
            data = ((resp.get("output_image") or {}).get("data"))
            if not data:
                raise AdsError("Gemini no devolvió una imagen")
            return base64.b64decode(data), "image/jpeg"
        body = {"contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect_ratio}}}
        resp = self._request("POST", f"{GEMINI_BASE}/v1beta/models/{self.model}:generateContent", headers, json.dumps(body).encode())
        for cand in resp.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"]), inline.get("mimeType") or inline.get("mime_type") or "image/png"
        raise AdsError("Gemini no devolvió una imagen")


def ext_for(mime):
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".img")


# ---- pedidos de Meta (puros: los usan `plan` y `create`) ------------------
def wa_link(ads):
    url = f"https://api.whatsapp.com/send?phone={ads['whatsapp_number']}"
    if ads.get("prefilled_message"):
        url += "&text=" + urllib.parse.quote(str(ads["prefilled_message"]))
    return url


def budget_minor(daily_budget):
    return int(round(float(daily_budget) * 100))  # [hipótesis] unidad mínima = centavos


def build_plan(cfg, page_id="PAGE_ID"):
    """Arma los pedidos de la campaña. No toca la red."""
    ads, name = cfg["ads"], cfg["name"]
    campaign = {"name": f"{name} — click a whatsapp", "objective": "OUTCOME_ENGAGEMENT",
                "status": "PAUSED", "special_ad_categories": []}
    adset = {"name": f"{name} — conjunto", "daily_budget": budget_minor(ads["daily_budget"]),
             "billing_event": "IMPRESSIONS", "optimization_goal": "CONVERSATIONS",
             "destination_type": "WHATSAPP", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "status": "PAUSED",
             "promoted_object": {"page_id": page_id, "whatsapp_phone_number": ads["whatsapp_number"]},
             "targeting": {"geo_locations": {"countries": list(ads["countries"])}, "age_min": int(ads.get("age_min") or 18),
                           "publisher_platforms": ["facebook", "instagram"]}}
    creatives = []
    for i, v in enumerate(ads["variants"], start=1):
        creatives.append({"variant": i, "name": f"{name} — creatividad {i}", "headline": v["headline"], "primary_text": v["primary_text"],
                          "object_story_spec": {"page_id": page_id, "link_data": {
                              "image_hash": f"<hash de la imagen {i}>", "link": wa_link(ads), "message": v["primary_text"],
                              "name": v["headline"], "call_to_action": {"type": "WHATSAPP_MESSAGE", "value": {"app_destination": "WHATSAPP"}}}}})
    return {"campaign": campaign, "adset": adset, "creatives": creatives}


class MetaAds:
    def __init__(self, token, account_id, page_id, api_version, request=None):
        if not (token and account_id and page_id and api_version):
            raise AdsError("faltan datos de Meta (token, cuenta publicitaria, página o versión)")
        self._token, self.page_id, self.version = token, page_id, api_version
        self.account = account_id if str(account_id).startswith("act_") else f"act_{account_id}"
        self._request = request or _http

    @classmethod
    def from_env(cls, env=None, request=None):
        env = os.environ if env is None else env
        miss = missing_env(META_ENV, env)
        if miss:
            raise AdsError("faltan variables de entorno: " + ", ".join(miss))
        return cls(env["META_ACCESS_TOKEN"], env["META_AD_ACCOUNT_ID"], env["META_PAGE_ID"], env["META_API_VERSION"], request)

    def __repr__(self):
        return f"MetaAds(account={self.account!r}, version={self.version!r})"

    def _post(self, path, fields):
        enc = {k: (json.dumps(v) if isinstance(v, (dict, list, bool)) else v) for k, v in fields.items()}
        enc["access_token"] = self._token  # en el cuerpo, no en la URL
        return self._request("POST", f"https://graph.facebook.com/{self.version}/{path}",
                             {"Content-Type": "application/x-www-form-urlencoded"}, urllib.parse.urlencode(enc).encode())

    def upload_image(self, data):
        resp = self._post(f"{self.account}/adimages", {"bytes": base64.b64encode(data).decode()})
        images = resp.get("images") or {}
        for v in images.values():
            if v.get("hash"):
                return v["hash"]
        raise AdsError("Meta no devolvió el hash de la imagen")

    def create(self, path, fields):
        r = self._post(path, fields)
        if not r.get("id"):
            raise AdsError(f"Meta no devolvió id al crear {path}")
        return r["id"]

    def set_status(self, object_id, status):
        return self._post(object_id, {"status": status})


# ---- orquestación ---------------------------------------------------------
def ads_dir(venture_dir):
    return os.path.join(venture_dir, "ads")


def load_cfg(venture_dir):
    with open(os.path.join(venture_dir, "venture.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def guard_copy(cfg):
    ads = cfg.get("ads") or {}
    bad = []
    for i, v in enumerate(ads.get("variants") or [], start=1):
        for field in ("headline", "primary_text"):
            for p in copy_problems(v.get(field), ads.get("extra_blocked_phrases") or ()):
                bad.append(f"variante {i}, {field}: '{p}'")
    return bad


def image_path(venture_dir, i):
    d = ads_dir(venture_dir)
    for ext in (".jpg", ".png", ".webp", ".img"):
        p = os.path.join(d, f"variante-{i}{ext}")
        if os.path.exists(p):
            return p
    return None


def generate_images(venture_dir, cfg, gemini, force=False, out=print):
    os.makedirs(ads_dir(venture_dir), exist_ok=True)
    done = []
    for i, v in enumerate(cfg["ads"]["variants"], start=1):
        if image_path(venture_dir, i) and not force:
            out(f"variante {i}: ya existe, no se vuelve a generar (usá --force)")
            continue
        data, mime = gemini.generate(v["image_prompt"], v.get("aspect_ratio") or "1:1")
        path = os.path.join(ads_dir(venture_dir), f"variante-{i}{ext_for(mime)}")
        with open(path, "wb") as f:
            f.write(data)
        done.append(path)
        out(f"variante {i}: {path}")
    return done


def create_campaign(venture_dir, cfg, meta, out=print):
    bad = guard_copy(cfg)
    if bad:
        raise AdsError("el texto tiene promesas que no se publican: " + "; ".join(bad))
    plan = build_plan(cfg, meta.page_id)
    paths = [image_path(venture_dir, i) for i in range(1, len(plan["creatives"]) + 1)]
    if not all(paths):
        raise AdsError("faltan imágenes: corré `python -m engine.ads images` primero")
    ids_path = os.path.join(ads_dir(venture_dir), "meta_ids.json")
    if os.path.exists(ids_path):
        raise AdsError(f"ya hay una campaña creada ({ids_path}); borrala a mano si querés crear otra")
    campaign_id = meta.create(f"{meta.account}/campaigns", plan["campaign"])
    adset_id = meta.create(f"{meta.account}/adsets", {**plan["adset"], "campaign_id": campaign_id})
    ad_ids = []
    for c, p in zip(plan["creatives"], paths):
        with open(p, "rb") as f:
            h = meta.upload_image(f.read())
        spec = json.loads(json.dumps(c["object_story_spec"]).replace(f"<hash de la imagen {c['variant']}>", h))
        creative_id = meta.create(f"{meta.account}/adcreatives", {"name": c["name"], "object_story_spec": spec})
        ad_ids.append(meta.create(f"{meta.account}/ads", {"name": c["name"], "adset_id": adset_id,
                                                          "creative": {"creative_id": creative_id}, "status": "PAUSED"}))
    ids = {"campaign": campaign_id, "adset": adset_id, "ads": ad_ids}
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)
    out("creado en PAUSA. Revisalo en el Administrador de anuncios antes de encender.")
    return ids


def activate(venture_dir, cfg, meta, confirmed, out=print):
    if not confirmed:
        raise AdsError("encender gasta plata real: repetí el comando con --confirmo-gasto")
    ids_path = os.path.join(ads_dir(venture_dir), "meta_ids.json")
    if not os.path.exists(ids_path):
        raise AdsError("no hay campaña creada: corré `create` primero")
    ids = json.load(open(ids_path, encoding="utf-8"))
    for oid in [*ids["ads"], ids["adset"], ids["campaign"]]:
        meta.set_status(oid, "ACTIVE")
    out(f"ACTIVA. Presupuesto diario: {cfg['ads']['daily_budget']} (moneda de tu cuenta publicitaria), países: {', '.join(cfg['ads']['countries'])}.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "images", "create", "activate"])
    ap.add_argument("venture_dir")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--confirmo-gasto", action="store_true")
    a = ap.parse_args(argv)
    from engine.envfile import load_env
    load_env()
    cfg = load_cfg(a.venture_dir)
    if not cfg.get("ads"):
        print("venture.yaml no tiene sección 'ads'")
        return 1
    try:
        if a.command == "plan":
            bad = guard_copy(cfg)
            if bad:
                print("PROMESAS A SACAR:", "; ".join(bad))
            print(json.dumps(build_plan(cfg), indent=2, ensure_ascii=False))
            return 1 if bad else 0
        if a.command == "images":
            generate_images(a.venture_dir, cfg, GeminiImages.from_env(), force=a.force)
        elif a.command == "create":
            create_campaign(a.venture_dir, cfg, MetaAds.from_env())
        else:
            activate(a.venture_dir, cfg, MetaAds.from_env(), a.confirmo_gasto)
    except AdsError as e:
        print(f"error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
