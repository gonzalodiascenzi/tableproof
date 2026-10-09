# Qué se verificó en la documentación de Meta (2026-10-08)

Regla de la casa: [verificado] con fuente y fecha, o [hipótesis]. Las páginas se leyeron con un resumidor automático de páginas, no a mano: contrastar con la página antes de lanzar. Varias páginas de `developers.facebook.com/docs/...` no abrieron; se usaron las que sí.

## [verificado]
- Verificación del webhook (GET): `hub.mode` siempre `subscribe`, `hub.verify_token` (el token que se configura en el panel) y `hub.challenge` (un entero que hay que devolver). Fuente: [Webhooks, getting started](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/).
- Firma de los POST: cabecera `X-Hub-Signature-256`, valor `sha256=` + firma SHA256 calculada con el payload y el App Secret. La página dice que validar es opcional pero recomendado. Misma fuente.
- Reintentos: Meta reintenta con frecuencia decreciente hasta 7 días si la respuesta no es 200, y eso puede generar notificaciones duplicadas. Payloads de hasta 3 MB. Fuente: [WhatsApp webhooks, overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview/).
- Estructura del mensaje entrante: `entry[].changes[].value.messages[]` con `from`, `id`, `timestamp` (texto), `type`, `text.body`; `contacts[].profile.name` y `wa_id`; `field` = `messages`. Fuente: [referencia del webhook de texto](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/text/) y el overview.
- Envío: `POST https://graph.facebook.com/{versión}/{phone_number_id}/messages` con `Authorization: Bearer`; texto = `messaging_product`, `to`, `type`, `text.body`; plantilla = `template.name` y `template.language.code`. Fuente: [referencia de mensajes](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/).

## [hipótesis] / no verificado
- La firma se calcula sobre los bytes crudos del cuerpo: la página dice solo "the payload". Se implementó sobre bytes crudos; probar con un payload real de Meta.
- Versión de la API: los ejemplos de la página usan v21.0, pero puede estar desactualizada. El código NO la tiene escrita: sale de `WHATSAPP_API_VERSION`. Mirar el changelog antes de elegirla.
- Estructura de `statuses[]` (estados de entrega): no la mostraba ninguna página leída. Se ignoran los estados.
- Timeout de respuesta del webhook y cuerpo de respuesta requerido: no los especificaba la página.
- Que no haya tolerancia de timestamp es una decisión propia: un reintento legítimo puede llegar días después, y un replay se frena por el `id` del mensaje.
- Los ids de mensajes procesados no se purgan antes de 8 días (por los 7 días de reintentos).
