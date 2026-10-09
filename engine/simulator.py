"""Simulador de consola: conversá con el respondedor sin conectar nada.

  python -m engine.simulator <flow.yaml> [--db archivo.sqlite]

Comandos: /optin  /avanzar <horas>  /seguimiento <plantilla>  /estado  /salir
"""
import argparse
import sys

from engine.flow import load_flow, validate_flow
from engine.responder import Clock, Responder
from engine.store import Store


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("flow")
    ap.add_argument("--db", default=":memory:")
    ap.add_argument("--phone", default="+000-simulador")
    a = ap.parse_args(argv)
    flow = load_flow(a.flow)
    errs = validate_flow(flow)
    if errs:
        print("flow inválido:\n- " + "\n- ".join(errs))
        return 1
    r = Responder(flow, Store(a.db), Clock())
    print("simulador (escribí /salir para terminar; /avanzar 25 para correr el reloj 25 h)")
    for line in sys.stdin if not sys.stdin.isatty() else iter(lambda: input("> "), None):
        line = line.strip()
        if line == "/salir":
            break
        if line == "/optin":
            r.record_opt_in(a.phone); print("[opt-in explícito registrado]")
        elif line.startswith("/avanzar"):
            r.clock.advance(hours=float(line.split()[1])); print(f"[reloj +{line.split()[1]} h]")
        elif line.startswith("/seguimiento"):
            out = r.follow_up(a.phone, template=line.split()[1])
            print("\n".join(f"bot: {m}" for m in out) or "[bloqueado: ver eventos]")
        elif line == "/estado":
            print(r.store.contact(a.phone))
        else:
            for m in r.handle_incoming(a.phone, line):
                print(f"bot: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
