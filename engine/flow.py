"""Esquema de flow.yaml y validador.

flow.yaml (un archivo por emprendimiento: ventures/<slug>/flow.yaml):

  version: 1
  name: <nombre>
  disclosure: <texto que se antepone al primer mensaje: asistente automático con una persona detrás>
  initial: <estado inicial>
  human_exit:                  # salida a humano, vale en TODOS los estados
    keywords: [persona, humano]
    message: <texto>
  stop:                        # baja inmediata
    keywords: [baja, stop]
    message: <texto>
  templates:                   # plantillas aprobadas por meta (nombre -> texto)
    seguimiento_24h: <texto>
  states:
    <estado>:
      message: <mensaje exacto del bot al entrar al estado>
      human_exit: true         # obligatorio en todo estado salvo los terminales
      reprompt: <texto si la respuesta no coincide (opcional)>
      transitions:             # por respuesta; la primera que coincide gana
        - {match: [si, dale], to: <estado>}
        - {default: true, to: <estado>}   # opcional
      terminal: true           # opcional: estado final (sin transiciones)
      free_value: true         # opcional: llegar a este estado = usó el valor gratis (métrica 2 del embudo)
"""
import yaml

REQUIRED_TOP = ("version", "name", "disclosure", "initial", "human_exit", "stop", "states")


def load_flow(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_flow(flow):
    """Devuelve la lista de errores (vacía = válido)."""
    errs = []
    if not isinstance(flow, dict):
        return ["el flow no es un mapa"]
    for k in REQUIRED_TOP:
        if k not in flow:
            errs.append(f"falta '{k}'")
    if errs:
        return errs
    if not str(flow["disclosure"]).strip():
        errs.append("'disclosure' vacío: el primer mensaje debe decir que es un asistente automático con una persona detrás")
    for blk in ("human_exit", "stop"):
        b = flow[blk]
        if not isinstance(b, dict) or not b.get("keywords") or not str(b.get("message", "")).strip():
            errs.append(f"'{blk}' necesita keywords y message")
        elif not all(isinstance(k, str) for k in b["keywords"]):
            errs.append(f"'{blk}': todas las keywords deben ser texto (entre comillas)")
    states = flow["states"]
    if not isinstance(states, dict) or not states:
        return errs + ["'states' vacío"]
    if flow["initial"] not in states:
        errs.append(f"el estado inicial '{flow['initial']}' no existe")
    for name, st in states.items():
        if not isinstance(st, dict) or not str(st.get("message", "")).strip():
            errs.append(f"estado '{name}': falta 'message'")
            continue
        if not st.get("terminal") and st.get("human_exit") is not True:
            errs.append(f"estado '{name}': sin salida a humano (human_exit: true)")
        trans = st.get("transitions") or []
        if not st.get("terminal") and not trans:
            errs.append(f"estado '{name}': no es terminal y no tiene transiciones")
        for i, t in enumerate(trans):
            if t.get("to") not in states:
                errs.append(f"estado '{name}': transición {i} apunta a '{t.get('to')}', que no existe (transición huérfana)")
            if not t.get("default") and not t.get("match"):
                errs.append(f"estado '{name}': transición {i} sin 'match' ni 'default'")
            for k in t.get("match") or []:
                if not isinstance(k, str):  # yaml convierte no/yes/on/off en booleanos
                    errs.append(f"estado '{name}': transición {i}: palabra clave {k!r} no es texto (poné \"no\"/\"si\" entre comillas)")
    # estados inalcanzables
    if flow["initial"] in states:
        seen, todo = set(), [flow["initial"]]
        while todo:
            s = todo.pop()
            if s in seen or s not in states:
                continue
            seen.add(s)
            todo += [t.get("to") for t in (states[s].get("transitions") or [])]
        for name in states:
            if name not in seen:
                errs.append(f"estado '{name}': inalcanzable desde '{flow['initial']}'")
    return errs
