# Probar el webhook en local

El código se probó con secretos de prueba inventados y sin red. Con credenciales reales de un número de prueba, estos son los pasos.

## Prueba sin Meta (ya funciona)
1. En una terminal, con secretos de prueba que elijas vos (no reales):
   `WHATSAPP_VERIFY_TOKEN=... WHATSAPP_APP_SECRET=... WHATSAPP_ACCESS_TOKEN=... WHATSAPP_PHONE_NUMBER_ID=... WHATSAPP_API_VERSION=... python -m engine.server <flow.yaml> --port 8080`
2. `python -m engine.devtools payload "hola" --from 5491100000000 > p.json`
3. `SIG=$(python -m engine.devtools sign p.json)` y
   `curl -X POST -H "X-Hub-Signature-256: $SIG" --data-binary @p.json http://127.0.0.1:8080/webhook`
4. Probá una firma mala (403), el mismo mensaje dos veces (procesa una) y el GET de verificación:
   `curl "http://127.0.0.1:8080/webhook?hub.mode=subscribe&hub.verify_token=<el tuyo>&hub.challenge=777"` (devuelve 777).

## Con un número de prueba de Meta (te toca a vos)
1. En el panel de Meta for Developers, crear o abrir la app, agregar WhatsApp y usar el número de prueba. Anotar el `phone_number_id`.
2. Cargar las cinco variables en el entorno donde corra el servidor (o en el panel de variables de tu hosting): `WHATSAPP_VERIFY_TOKEN` (lo inventás vos), `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION` (mirar la vigente en el changelog de Meta). No las escribas en ningún archivo del repo ni en el chat.
3. Exponer el servidor con una URL https pública (túnel o hosting) y configurarla en el panel como URL de callback del webhook, con el mismo verify token; suscribirse al campo `messages`.
4. Cargar las plantillas (ver `docs/plantillas-a-aprobar.md`) y enviarlas a aprobar desde el panel. El código no las envía.
5. Escribir al número de prueba desde un teléfono agregado como destinatario de prueba.

## Plantillas
`python -m engine.templates <flow.yaml>` imprime los textos de `templates:` listos para cargar. Los de los tests son de ejemplo ficticio; los reales salen del flow de cada emprendimiento.
