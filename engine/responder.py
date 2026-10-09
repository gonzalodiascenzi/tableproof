"""Respondedor como máquina de estados. Sin red, sin API externa.

Reglas que el motor hace cumplir (no dependen de que el flow las respete):
- el primer mensaje del bot lleva siempre el `disclosure` del flow;
- salida a humano por palabra clave en CUALQUIER estado; mientras hay un
  humano a cargo el bot no responde;
- "baja"/"stop" corta de inmediato y registra la fecha; después no se envía
  nada (ni plantillas) hasta un opt-in explícito nuevo;
- ventana de atención de 24 h desde el último mensaje del cliente: dentro se
  responde libre; fuera solo una plantilla aprobada a quien dio opt-in explícito;
- opt-in con fecha: [hipótesis] el primer mensaje del cliente habilita
  responderle dentro de la ventana (fuente 'mensaje_entrante'); los mensajes
  iniciados por la empresa exigen un opt-in explícito (`record_opt_in`).
- mensajes desordenados (ts anterior al último procesado) se registran pero
  no mueven el estado.
"""
import re
import time

WINDOW_SECONDS = 24 * 3600


class Clock:
    """Reloj controlable para probar la ventana de 24 h."""
    def __init__(self, start=1_700_000_000.0):
        self.t = float(start)

    def now(self):
        return self.t

    def advance(self, hours=0, seconds=0):
        self.t += hours * 3600 + seconds


class RealClock:
    """Reloj real para producción (la ventana de 24 h usa la hora de Meta/UTC)."""
    def now(self):
        return time.time()


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def _has_keyword(text, keywords):
    t = _norm(text)
    return any(re.search(rf"(?<!\w){re.escape(_norm(k))}(?!\w)", t) for k in keywords)


class Responder:
    def __init__(self, flow, store, clock=None):
        self.flow, self.store, self.clock = flow, store, clock or Clock()

    # ---- opt-in / ventana -------------------------------------------------
    def record_opt_in(self, phone, source="explicito"):
        self.store.ensure(phone)
        self.store.update(phone, opt_in_at=self.clock.now(), opt_in_source=source, opt_out_at=None)
        self.store.log(phone, self.clock.now(), "sistema", None, f"opt_in:{source}")

    def window_open(self, phone):
        c = self.store.contact(phone)
        return bool(c and c["last_user_at"] is not None and self.clock.now() - c["last_user_at"] <= WINDOW_SECONDS)

    # ---- entrada ----------------------------------------------------------
    def handle_incoming(self, phone, text, ts=None):
        """Devuelve la lista de mensajes que el bot envía (puede ser vacía)."""
        ts = self.clock.now() if ts is None else ts
        c = self.store.ensure(phone)
        late = c["last_user_at"] is not None and ts < c["last_user_at"]
        self.store.log(phone, ts, "in", text, "desordenado" if late else None)
        if late:
            return []  # llegó tarde: no mueve el estado ni responde de nuevo
        first = c["state"] is None
        self.store.update(phone, last_user_at=ts)
        if first and c["opt_in_at"] is None:
            self.store.update(phone, opt_in_at=ts, opt_in_source="mensaje_entrante")
            self.store.log(phone, ts, "sistema", None, "opt_in:mensaje_entrante")

        stop = self.flow["stop"]
        if _has_keyword(text, stop["keywords"]):
            if c["opt_out_at"] is None:
                self.store.update(phone, opt_out_at=ts)
                return self._send(phone, [stop["message"]], ts)
            return []
        if c["opt_out_at"] is not None:
            return []  # dio de baja: silencio hasta un opt-in explícito nuevo

        he = self.flow["human_exit"]
        if c["human"]:
            return []  # una persona está a cargo
        if _has_keyword(text, he["keywords"]):
            self.store.update(phone, human=1)
            return self._send(phone, [he["message"]], ts)

        states = self.flow["states"]
        if first:
            state = self.flow["initial"]
            self.store.update(phone, state=state)
            msg = f"{self.flow['disclosure'].strip()}\n\n{states[state]['message'].strip()}"
            return self._send(phone, [msg], ts)

        st = states[c["state"]]
        target = None
        for t in st.get("transitions") or []:
            if t.get("default"):
                target = target or t["to"]
            elif _has_keyword(text, t["match"]):
                target = t["to"]
                break
        if target is None:
            return self._send(phone, [st.get("reprompt") or st["message"]], ts)
        self.store.update(phone, state=target)
        return self._send(phone, [states[target]["message"].strip()], ts)

    # ---- salida iniciada por la empresa ----------------------------------
    def follow_up(self, phone, template=None, free_text=None):
        """Seguimiento. Dentro de la ventana: texto libre o plantilla. Fuera: solo
        plantilla aprobada y solo con opt-in explícito. Devuelve [] si se bloquea."""
        now = self.clock.now()
        c = self.store.contact(phone)
        if not c or c["opt_out_at"] is not None or c["human"]:
            self.store.log(phone, now, "bloqueado", free_text or template, "baja_o_humano")
            return []
        if self.window_open(phone):
            body = free_text or (self.flow["templates"].get(template) if template else None)
            if body:
                return self._send(phone, [body], now)
            return []
        if template in (self.flow.get("templates") or {}) and c["opt_in_source"] == "explicito":
            return self._send(phone, [self.flow["templates"][template]], now, note=f"plantilla:{template}")
        self.store.log(phone, now, "bloqueado", free_text or template, "ventana_vencida")
        return []

    def _send(self, phone, msgs, ts, note=None):
        for m in msgs:
            self.store.log(phone, ts, "out", m, note)
        return msgs

    def release_human(self, phone):
        self.store.update(phone, human=0)
