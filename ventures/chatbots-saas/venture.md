# chatbots saas

segundo caso del framework. origen: ingrediente `chatbase` de seedproof (`ingrediente.json`). estado: idea, flujo en borrador, producto escrito y sin probar contra la API real.

## 0. ficha

- nombre: [completar: marca propia]. chatbase es la referencia, no el nombre: usarlo confundiría con otra empresa (sección 4).
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

- oferta: [completar]. borrador: "un chatbot para tu web que contesta las preguntas de tus clientes con la info de tu negocio".
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
- [ ] salida clara a humano
- [ ] no pido ni comparto identificadores sensibles
- [ ] el nombre no suplanta ni confunde: no usar "chatbase"
- [ ] la IA no es la funcionalidad principal que se ofrece por la plataforma (cláusula 4.7)
- [ ] los chats no se usan para entrenar modelos
- [ ] política de privacidad publicada
- [ ] bajas y bloqueos inmediatos

[inferencia, no verificada con meta] sobre la cláusula 4.7: acá whatsapp es el canal de venta y el chatbot se entrega en la web del cliente, así que la IA no se ofrece dentro de whatsapp. cambia si el producto pasa a ser "un chatbot para tu whatsapp": ahí la IA sería lo que se ofrece por la plataforma. meta decide a su criterio.

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

## 9. riesgos abiertos

1. el producto está escrito (`producto/README.md`) pero no se probó contra la API de Claude ni en un navegador, y no está publicado. falta: clave de la API, un dominio https, y completar `access_url` (el panel) y el link de la demo en `flow.yaml`. dueño: gonzalo.
2. recargas. el cobro es por paquete con pago único (sin suscripciones), pero el motor admite un solo pedido por teléfono (`docs/mvp-punta-a-punta.md`): el cliente no puede comprar la recarga desde el mismo whatsapp. hay que levantar ese límite en `engine/payments.py` antes de vender recargas. [hipótesis] que el comercio prefiera pagar por paquete y no un abono fijo como cobra chatbase. dueño: gonzalo.
3. cláusula 4.7 de meta, ver sección 4. dueño: gonzalo. revisar antes de lanzar.
4. costo por conversación del modelo de IA, sin dato. chatbase no publica costos. define si el precio en pesos deja margen y qué modelo usar (`CHATBOT_MODEL`). se mide con `producto/server.py uso`. dueño: gonzalo.
5. la demo gratis también gasta en el modelo de IA y es pública. tiene un tope diario y uno por IP (`producto/bot.py`, valores técnicos por defecto); el dueño decide si esos valores le sirven.
6. fiscal y legal (facturación, términos del servicio, datos de los clientes de los clientes). dueño: gonzalo, con contador y asesoría legal. no investigado.
