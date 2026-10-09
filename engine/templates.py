"""Imprime las plantillas de un flow listas para cargarlas y mandarlas a aprobar a mano."""
import sys

from engine.flow import load_flow


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    flow = load_flow(argv[0])
    print(f"# plantillas a aprobar: {flow['name']}\n")
    print("Las carga y envía a aprobar el dueño desde el panel de Meta. Este código no las envía.\n")
    for name, text in (flow.get("templates") or {}).items():
        print(f"## {name}\n\n{text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
