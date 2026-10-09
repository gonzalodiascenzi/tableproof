"""Herramientas para probar el webhook en local con un secreto de PRUEBA que elegís vos.

  python -m engine.devtools payload "hola" --from 5491100000000 > payload.json
  python -m engine.devtools sign payload.json          # imprime X-Hub-Signature-256 (usa WHATSAPP_APP_SECRET del entorno)
"""
import json
import os
import sys
import time

from engine import whatsapp as wa


def example_payload(text, sender, msg_id=None, ts=None):
    return {"object": "whatsapp_business_account", "entry": [{"id": "TEST", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"display_phone_number": "TEST", "phone_number_id": "TEST"},
        "contacts": [{"profile": {"name": "Prueba"}, "wa_id": sender}],
        "messages": [{"from": sender, "id": msg_id or f"wamid.TEST{int(time.time()*1000)}",
                      "timestamp": str(int(ts or time.time())), "type": "text", "text": {"body": text}}]}}]}]}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["payload"]:
        sender = argv[argv.index("--from") + 1] if "--from" in argv else "0000000000"
        sys.stdout.write(json.dumps(example_payload(argv[1], sender)))
        return 0
    if argv[:1] == ["sign"]:
        secret = os.environ.get("WHATSAPP_APP_SECRET")
        if not secret:
            print("falta WHATSAPP_APP_SECRET en el entorno")
            return 1
        print(wa.sign(open(argv[1], "rb").read(), secret))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
