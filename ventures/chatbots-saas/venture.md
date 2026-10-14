# chatbots saas: MostradorBot

segundo caso del framework. origen: ingrediente `chatbase` de seedproof (`ingrediente.json`). estado: idea, marca y textos propuestos, producto escrito y sin probar contra la API real.

## 0. ficha

- nombre: MostradorBot (propuesta de Claude, 2026-10-14, a aprobar por el dueño). chatbase es la referencia, no el nombre.
  - por qué: "el mostrador de tu web", la idea de un comercio de barrio que atiende consultas.
  - descartados por choque con productos existentes [verificado 2026-10-14, búsqueda web]: "Contestalo" (contestalo.com, recepcionista con IA para inmobiliarias), "Atendé" (Atendi, atendiapp.com), "Respondón" (Responde.ai, responde.app).
  - [verificado 2026-10-14] la búsqueda web no encontró otro producto llamado MostradorBot; mostradorbot.com, .com.ar y .ar no resolvían en DNS (probablemente libres).
  - [hipótesis] que la marca esté libre en el INPI y que los dominios se puedan registrar: no se consultó el INPI ni NIC Argentina. "El Mostrador" es un diario chileno, de otro rubro.
- fecha de inicio: 2026-10-14
- estado: idea
- dueño de la decisión de corte: gonzalo

## 1. hipótesis falsable

- [hipótesis] [N] comercios chicos argentinos con web propia pagan [$X] por paquete de consultas de un chatbot que contesta las preguntas de sus clientes con la info del negocio. N y X los define el dueño.
- por qué creo que es cierta:
  - [verificado 2026-10-13, seedproof] chatbase, un saas de chatbots, muestra $863.632 de mrr y 12.424 suscripciones en trustmrr; supabase publica un arr superior a $10 m. fuentes: https://trustmrr.com/startup/chatbase, https://supabase.com/customers/chatbase
  - [verificado, misma fuente] salvedades de ese dato: la clave de stripe en trustmrr figura vencida, hoy son 18 personas y los costos no están publicados.
  - [hipótesis] que exista esa demanda en comercios chicos de argentina, en pesos y vendida por whatsapp. el caso de chatbase prueba la categoría, no este mercado. no hay dato propio.

## 2. oferta en una línea

- oferta: "MostradorBot es un chat para tu web que contesta las preguntas de tus clientes con la info de tu negocio." (propuesta, a aprobar)
- gratis (puerta de entrada): probar un chatbot de ejemplo por link, sin registrarse (`producto/`, ruta `/demo`, negocio ficticio).
- pago: por uso, prepago (decisión del dueño, 2026-10-14). se paga un paquete de consultas con un pago único; cada respuesta del chatbot descuenta una; sin saldo, se recarga con otro paquete. el tamaño del paquete y su precio los define el dueño (`CHATBOT_PACK_MESSAGES`, `price_ars`).
- precio: lo define el dueño (`price_ars` en `venture.yaml`).
- límite que se declara de entrada: [hipótesis] el chatbot contesta con lo que el negocio le cargó y puede equivocarse; no reemplaza la atención de una persona.

## 3. flujo de whatsapp

borrador en `flow.yaml`. se prueba con `python -m engine.simulator ventures/chatbots-saas/flow.yaml`.

1. entrada: anuncio click-to-whatsapp con mensaje pre-armado.
2. saludo: qué es el producto en una línea y pregunta si quiere probar el ejemplo.
3. valor gratis: link a la demo (estado `demo`, marcado `free_value`). la demo es la ruta `/demo` del producto.
4. oferta: precio, límite declarado y link de pago.
5. seguimiento: sin plantillas todavía (`templates: {}`). van solo con plantilla aprobada y opt-in.
6. salida a humano: escribiendo "persona" en cualquier paso (lo hace cumplir el motor).

el flujo no tiene preguntas de calificación: el motor avanza por palabras clave y no guarda respuestas libres.

## 4. cumplimiento (política de meta)

verificado el 2026-10-08 para scamproof (ver `ventures/_archivo/scamproof/venture.md`, sección 4). releer antes de lanzar.

- [ ] solo escribo a quien me dio su número y aceptó recibir mensajes
- [ ] fuera de las 24 h solo plantillas aprobadas
- [x] salida clara a humano (la hace cumplir el motor: "persona" en cualquier paso)
- [ ] no pido ni comparto identificadores sensibles
- [x] el nombre no suplanta ni confunde: no usar "chatbase" (MostradorBot; ver sección 0 para los descartados)
- [ ] la IA no es la funcionalidad principal que se ofrece por la plataforma (cláusula 4.7)
- [ ] los chats no se usan para entrenar modelos
- [ ] política de privacidad publicada
- [x] bajas y bloqueos inmediatos (los hace cumplir el motor: "baja" o "stop")

[inferencia, no verificada con meta] sobre la cláusula 4.7: acá whatsapp es el canal de venta y el chatbot se entrega en la web del cliente, así que la IA no se ofrece dentro de whatsapp. cambia si el producto pasa a ser "un chatbot para tu whatsapp": ahí la IA sería lo que se ofrece por la plataforma. meta decide a su criterio.

## 4b. competencia en argentina

[verificado 2026-10-14, búsqueda web leída con resumidor; precios según cada página, sin contrastar a mano]

- OwnKeyBot (ownkeybot.com/es-ar): chatbot para la web que contesta con la información de la empresa. es el mismo producto.
- Responde.ai (respondeai.co): plan gratis de 1 chatbot y 100 mensajes por mes; pagos de $29 a $49 por mes.
- Atendi (atendiapp.com, Buenos Aires): bot para whatsapp, instagram y tiktok; plan básico de USD 50 por mes.
- Cliengo, 360 ChatBot, Zasbot y Botmaker también venden chatbots para empresas en argentina.
- Nexent (nexent.com.ar): implementación desde USD 300 más mantenimiento.

lo que diferencia a MostradorBot hoy: venta y alta por whatsapp en minutos, sin abono, pago en pesos por paquete. [hipótesis] que eso alcance contra competidores con plan gratis y más canales: es lo que mide el test.

## 5. test chico

- presupuesto máximo de gasto: lo define el dueño
- duración: lo define el dueño
- público: [hipótesis] comercios chicos argentinos con web propia
- una conversación cuenta cuando la persona manda un segundo mensaje (criterio del motor, `engine/funnel.py`)

## 6. tres números

| métrica | cómo se mide | valor |
|---|---|---|
| costo por conversación iniciada | gasto en anuncios / conversaciones | sin dato |
| % que usa el valor gratis | llegaron al estado `demo` / conversaciones | sin dato |
| % que paga | pagaron / usaron gratis | sin dato |

## 7. criterio de corte y de escala

los pone el dueño antes de gastar, en una copia de `framework/metricas.plantilla.yaml`.

- se mata si:
- se corrige una vez si:
- se escala si:

## 8. bitácora

2026-10-14 | se armó la carpeta desde el ingrediente chatbase y se escribió el borrador del flujo | sin número | pendiente decidir marca, precio y modelo de cobro
2026-10-14 | el dueño definió el modelo de cobro: lo gratis es gratis y cada uno paga por lo que usa (paquetes prepagos de consultas) | sin número | pendiente tamaño y precio del paquete, y habilitar la recarga en el motor
2026-10-14 | se escribió el producto en `producto/` (panel, widget, demo, topes de uso), con tests sin red | sin número | pendiente probarlo con una clave de la API y publicarlo en un dominio
2026-10-14 | se fusionó el PR 1. se propuso la marca MostradorBot y se escribieron los textos del flow, de la entrega y de dos anuncios. se habilitó la recarga en el motor (`repeat_purchase`) | sin número | ver sección 10

## 9. riesgos abiertos

1. el producto está escrito (`producto/README.md`) pero no se probó contra la API de Claude ni en un navegador, y no está publicado. falta: clave de la API, un dominio https, y completar `access_url` (el panel) y el link de la demo en `flow.yaml`. dueño: gonzalo.
2. recargas: resuelto en el código. con `repeat_purchase: true` el mismo whatsapp compra otro paquete cuando el anterior ya se entregó (`engine/checkout.py`). sigue abierto: [hipótesis] que el comercio prefiera pagar por paquete y no un abono fijo como cobra la competencia (sección 4b). dueño: gonzalo.
3. cláusula 4.7 de meta, ver sección 4. dueño: gonzalo. revisar antes de lanzar.
4. costo por conversación del modelo de IA, sin dato. chatbase no publica costos. define si el precio en pesos deja margen y qué modelo usar (`CHATBOT_MODEL`). se mide con `producto/server.py uso`. dueño: gonzalo.
5. la demo gratis también gasta en el modelo de IA y es pública. tiene un tope diario y uno por IP (`producto/bot.py`, valores técnicos por defecto); el dueño decide si esos valores le sirven.
6. fiscal y legal (facturación, términos del servicio, datos de los clientes de los clientes). dueño: gonzalo, con contador y asesoría legal. no investigado.
7. competencia con plan gratis y más canales (sección 4b). dueño: gonzalo. lo mide el test.

## 10. pendientes para lanzar

se tachan a medida que se resuelven. `python -m engine.check ventures/chatbots-saas` muestra los que bloquean el arranque.

**hechos (2026-10-14)**
- [x] marca: MostradorBot (propuesta; falta tu aprobación y consultar el INPI)
- [x] textos del flow de whatsapp, de la entrega y de los mensajes de error (propuesta)
- [x] dos variantes de anuncio que pasan la guarda de promesas (`python -m engine.ads plan ventures/chatbots-saas`)
- [x] recarga desde el mismo whatsapp (`repeat_purchase`)
- [x] `engine.ads plan` funciona antes de que definas presupuesto y países (antes fallaba)

**decisiones tuyas (sin valor por defecto)**
- [ ] aprobar marca y textos, o cambiarlos
- [ ] cantidad de consultas por paquete: `CHATBOT_PACK_MESSAGES` y el texto de la oferta en `flow.yaml`
- [ ] precio del paquete: `price_ars`
- [ ] anuncios: presupuesto diario (`ads.daily_budget`) y países (`ads.countries`)
- [ ] umbrales de corte y de escala (sección 7)
- [ ] modelo de Claude (`CHATBOT_MODEL`), mejor después de medir el costo con `server.py uso`

**cuentas y credenciales (las creás vos: ver `credenciales.md`)**
- [ ] dominio, por ejemplo mostradorbot.com.ar, con dos subdominios: venta y app
- [ ] número de whatsapp business y app de meta: `WHATSAPP_*`, y el número en `ads.whatsapp_number`
- [ ] mercado pago: `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET` (primero de prueba)
- [ ] clave de la API de Claude: `ANTHROPIC_API_KEY`
- [ ] anuncios (opcional): `GEMINI_*` y `META_*`

**publicar y probar**
- [ ] servidor de venta (`engine/app.py`) y del producto (`producto/server.py`) en https, con disco persistente
- [ ] completar las urls de `venture.yaml` y el link de la demo en `flow.yaml`
- [ ] probar la demo y el panel en un navegador, con la API real
- [ ] compra de punta a punta con credenciales de prueba (whatsapp de prueba + sandbox de mercado pago)
- [ ] política de privacidad publicada (sección 4)
- [ ] levantar la guardia de modo de prueba de pagos para cobrar de verdad (`docs/mvp-punta-a-punta.md`)
- [ ] facturación y términos del servicio, con contador y asesoría legal
