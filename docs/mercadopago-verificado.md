# Mercado Pago: qué se verificó y qué sigue como hipótesis (2026-10-08)

Regla de la casa: [verificado] con fuente y fecha, o [hipótesis]. Las páginas se leyeron con un resumidor automático de páginas: contrastar con la página antes de lanzar. Las páginas de referencia de la API (`/reference/...`) no abrieron, y la pestaña "Sin SDKs" de la validación de firma aparece vacía en lo que se leyó.

## [verificado]
- Webhooks: se configuran en Tus integraciones > Webhooks > Configurar notificaciones, con una URL https y el evento Pagos; al guardar se genera una clave secreta (sin vencimiento, se recomienda renovarla). Hay un botón "Simular" para probar. Fuente: [notificaciones de pago](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/payment-notifications) y [webhooks](https://www.mercadopago.com.ar/developers/es/docs/your-integrations/notifications/webhooks).
- Cuerpo de la notificación de pagos: `action`, `api_version`, `data.id`, `date_created`, `id`, `live_mode`, `type`, `user_id`. Misma fuente.
- La cabecera `x-signature` tiene la forma `ts=...,v1=...`; se leen también `x-request-id` y el parámetro `data.id` de la consulta. Misma fuente.
- Hay que responder HTTP 200 o 201 en 22 segundos; si no, reintenta (el texto dice cada 15 minutos; el diagrama muestra demoras crecientes hasta 96 h: la página se contradice y no dice cuántos reintentos hay). Misma fuente.
- Después de responder, se consulta el pago con `GET v1/payments/{id}`. Misma fuente.
- Una preferencia de pago se crea por cada pedido (items con `title`, `quantity`, `unit_price`). Fuente: [crear preferencia](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/create-payment-preference).
- Suscripciones: cobros recurrentes con frecuencia semanal, mensual o anual, con o sin plan; el primer pago va por un link. Fuente: [suscripciones](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/overview). Disponible en AR, entre otros países.

- Firma (contrastada 2026-10-08 con la versión `.md` de [payment-notifications](https://www.mercadopago.com.uy/developers/en/docs/checkout-pro/payment-notifications.md), leída con resumidor): manifiesto `id:{data.id};request-id:{x-request-id};ts:{ts};` (se omite el par cuyo valor no viene), HMAC-SHA256 con la clave secreta, en hexadecimal, comparado con `v1`; 200 si coincide, 401 si no. El código ya omite los pares ausentes. Reintentos documentados: 0, 15 min, 30 min, 6 h, 48 h, 96 h.
- Sigue como [hipótesis] solo el detalle de minúsculas: la prosa no lo dice, pero los SDK de ejemplo (Java, Ruby) pasan `data.id` a minúsculas; el código lo hace si es alfanumérico. Probar con el botón "Simular" antes de confiar.

## [hipótesis] (no estaba en lo leído; implementado así y a contrastar)
- El valor de `status` de un pago aprobado: `"approved"`. La página no listaba los valores.
- El endpoint `POST /checkout/preferences` y sus campos (`external_reference`, `notification_url`, `currency_id`, `init_point` en la respuesta): las páginas de referencia no abrieron. Es la parte menos segura; no se probó contra la API real.
- Cómo se usan las credenciales de prueba y el sandbox: las páginas de pruebas no se leyeron.

## Qué modelo de cobro encaja
- Un producto o servicio por pedido (se entrega una vez por pago): link de pago con una preferencia por pedido (Checkout Pro). Es lo que implementa el motor.
- Un abono recurrente (acceso mensual): suscripciones, con otros temas de webhook que la documentación leída no describía. NO está implementado; se decide con el emprendimiento y se lee su documentación antes.

## Límites conocidos
- Pago duplicado aprobado para un pedido ya cobrado: no se entrega dos veces y se avisa al dueño. Reembolso o contracargo (nombres de estado [hipótesis]: refunded, charged_back, cancelled): no se revierte nada solo, se avisa al dueño para revisión manual.
- Si la entrega falla después de los reintentos, el pedido queda en `entrega_fallida`, el cliente recibe el aviso de cómo hablar con una persona y el dueño recibe la alerta. No hay reintento automático posterior: lo resuelve una persona.
- Impuestos y facturación: no investigados.
