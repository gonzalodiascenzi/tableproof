# framework de ventures

motor compartido y una carpeta por emprendimiento.

- `framework/`: la plantilla (`framework-emprendimiento.md`) y el checklist de whatsapp (`whatsapp-checklist.md`).
- `ventures/<slug>/venture.md`: un emprendimiento, a partir de un ingrediente de seedproof (`python -m engine.scaffold`).
- `ventures/chatbots-saas/`: primer emprendimiento en borrador, a partir del ingrediente `chatbase`. incluye su producto en `producto/` (ver su README). no arranca hasta que el dueño complete marca, precio y dominios.
- `ventures/_archivo/`: casos descartados. `scamproof` está archivado: ver su motivo al inicio de su archivo.
- reglas: `CLAUDE.md`.

## motor del respondedor (prompt 5)

- `engine/flow.py`: esquema de `flow.yaml` (documentado en el docstring) y validador. Falla si un estado no tiene salida a humano, si hay transiciones huérfanas o estados inalcanzables, y si una palabra clave es un booleano de yaml (poné `"no"` entre comillas).
- `engine/responder.py`: máquina de estados. El motor, no el flow, hace cumplir: aviso de asistente automático en el primer mensaje, salida a humano en cualquier estado, baja inmediata, ventana de 24 h y opt-in con fecha.
- `engine/store.py`: estado y eventos en sqlite.
- `engine/simulator.py`: `python -m engine.simulator <flow.yaml>` para conversar sin conectar nada (`/avanzar 25` corre el reloj, `/optin`, `/seguimiento <plantilla>`).
- tests: `python -I -W ignore -m unittest discover -s tests -t .`. El flow de `tests/fixtures/` es ficticio; no hay flow de ningún emprendimiento real todavía.
- [hipótesis] el primer mensaje del cliente habilita responderle dentro de la ventana; los mensajes iniciados por la empresa exigen un opt-in explícito. Contrastar con la política de meta antes de lanzar.

## conexión con whatsapp cloud api (prompt 6)

- `engine/whatsapp.py`: verificación del GET, firma `X-Hub-Signature-256`, parseo del payload y envío por la Cloud API. Los secretos salen solo de variables de entorno y no se loguean.
- `engine/webhook.py`: rechaza firmas inválidas (403), procesa cada mensaje una sola vez (idempotencia por id) y entrega al respondedor.
- `engine/server.py`: servidor local para pruebas. `docs/whatsapp-local.md`: cómo probarlo y qué pasos manuales te tocan.
- `docs/meta-verificado.md`: qué se verificó en la documentación de Meta, con fecha, y qué sigue como hipótesis (firma sobre bytes crudos, versión de la API).

## cobro con mercado pago y entrega (prompt 7)

- `engine/payments.py`: pedidos, cliente de Mercado Pago (solo modo de prueba), verificación de firma, handler de notificaciones y entrega con reintentos. Todo en sqlite: pedidos, eventos de pago y de entrega.
- la entrega se activa solo tras una notificación con firma válida y la confirmación del pago consultando la API (estado, monto, moneda y referencia del pedido). Un mensaje o una captura del cliente no llega a la entrega: hay tests que lo comprueban.
- el precio sale de la config del emprendimiento (`price_ars`, lo define el dueño; sin precio no se crea ningún pedido).
- `docs/mercadopago-verificado.md`: qué se verificó, con fecha y fuente, y qué sigue como hipótesis (formato de la firma, valor de `status`, creación de la preferencia). Suscripciones no implementadas.
- credenciales: solo de prueba y solo por variables de entorno (`MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`, `MP_MODE=test`).

## métricas y criterio de corte (prompt 8)

- `engine/funnel.py` y `engine/report.py`: reporte diario en markdown con fecha, con los tres números de la sección 6 de la plantilla. `python -m engine.report --synthetic` lo prueba con datos sintéticos.
- una conversación cuenta cuando la persona manda un segundo mensaje (contesta la primera pregunta). "Usó el valor gratis" = llegó a un estado del flow marcado `free_value: true`; si el flow no tiene ninguno, el reporte no inventa la métrica y pregunta cuál la reemplaza.
- el gasto en anuncios se carga a mano (`framework/gasto_anuncios.plantilla.csv`, columnas `fecha,monto_ars`); sin filas, el costo por conversación es "sin dato".
- los umbrales los completa el dueño (`framework/metricas.plantilla.yaml`). Vacíos, el reporte dice "umbrales sin definir" y no recomienda nada. Con muestra chica, o sin `muestra_minima` definida, muestra "x de n" y no evalúa ninguna regla. Aun con reglas cumplidas, solo informa cuál; la decisión es del dueño.

## mvp de venta punta a punta (prompt 9)

anuncio con imagen de gemini → meta ads (click a whatsapp, en pausa) → respondedor → link de mercado pago → entrega automática. guía: `docs/mvp-punta-a-punta.md`.

- `engine/scaffold.py`: arma `ventures/<slug>/` desde `ventures/_plantilla/` a partir de un ingrediente de seedproof (`data/ingredients.json` de ese repo). el precio, el presupuesto y los países quedan para el dueño.
- `engine/venture.py` y `engine/check.py`: `python -m engine.check ventures/<slug>` verifica venta, flow, anuncios, textos `[completar ...]` y variables de entorno faltantes (solo nombres).
- `engine/checkout.py`: el flow escribe `{pay_link}` y se reemplaza al enviar por el link de pago de ese pedido.
- `engine/delivery.py`: entrega `access` (clave de licencia + `/verify`) o `download` (link firmado que vence y con tope de descargas).
- `engine/ads.py`: `plan`, `images`, `create`, `activate`. todo en pausa; encender exige `--confirmo-gasto`. `docs/ads-verificado.md` separa lo verificado de lo hipotético.
- `engine/app.py`: un solo servidor con `/webhook`, `/mp`, `/d/<token>`, `/verify` y `/health`. `Dockerfile` incluido.
- el modo de prueba de `engine/payments.py` sigue como estaba: levantarlo es decisión del dueño (ver la guía).
