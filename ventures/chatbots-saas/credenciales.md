# credenciales de MostradorBot: qué crear, dónde y en qué variable va

las cuentas se crean a tu nombre (piden tu identidad, tu cuenta bancaria o tu tarjeta), así que no las puede crear el código ni Claude. los valores van en `.env` (no se commitea) o en las variables del hosting; nunca en el repo ni en un chat.

regla de la casa: [verificado] con fuente y fecha, o [hipótesis]. las fuentes de whatsapp, mercado pago y anuncios están en `docs/`.

orden sugerido: 1 y 2 primero (sin ellos no hay nada que probar), después 3, 4 y 5, y los anuncios al final.

## 1. dominio

- qué: un dominio con dos subdominios, uno para el servidor de venta y otro para el producto. sugerencia: `mostradorbot.com.ar` con `venta.` y `app.`.
- dónde: NIC Argentina para `.com.ar` y `.ar`.
- [hipótesis] que esté libre: el 2026-10-14 no resolvía en DNS, pero no se consultó NIC Argentina. tampoco se verificaron los requisitos de alta en NIC.
- va en: `public_base_url`, `notification_url` y `access_url` de `venture.yaml`, y el link de la demo en `flow.yaml`.

## 2. clave de la API de Claude

- qué: la clave que usa el producto para contestar.
- dónde: la consola de Claude (platform.claude.com), en la sección de claves de API. se cargan créditos antes de usarla.
- variable: `ANTHROPIC_API_KEY`.
- consejo: ponele un límite de gasto mensual en la consola, además de los topes del producto.

## 3. mercado pago (primero de prueba)

- qué: la cuenta que cobra los paquetes.
- dónde: mercadopago.com.ar/developers, "Tus integraciones": crear una aplicación y copiar las credenciales de prueba.
- [verificado 2026-10-08, `docs/mercadopago-verificado.md`] el webhook se configura en Tus integraciones > Webhooks > Configurar notificaciones, con la url `https://<venta>/mp` y el evento Pagos; al guardar se genera la clave secreta.
- variables: `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`, `MP_MODE=test`.
- el motor solo acepta el modo de prueba. cobrar de verdad es un paso aparte (`docs/mvp-punta-a-punta.md`).

## 4. whatsapp business (cloud api)

- qué: el número que atiende a quien viene de los anuncios.
- dónde: Meta for Developers: crear una app, agregarle WhatsApp y empezar con el número de prueba (`docs/whatsapp-local.md`).
- [verificado 2026-10-08, `docs/meta-verificado.md`] el webhook se valida con un verify token que inventás vos y cada POST trae la firma `X-Hub-Signature-256` hecha con el App Secret.
- variables: `WHATSAPP_VERIFY_TOKEN` (lo inventás), `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`.
- [hipótesis] para un número propio (no el de prueba) y un token que no venza, Meta suele pedir verificar el negocio y crear un usuario del sistema. no se leyó esa documentación.
- url del webhook: `https://<venta>/webhook`, suscripto al campo `messages`.

## 5. servidor

- qué: dos procesos, el de venta (`python -m engine.app ventures/chatbots-saas`, o el Dockerfile) y el del producto (`python ventures/chatbots-saas/producto/server.py`), cada uno con https y una base sqlite en un disco que no se borre.
- variables del producto: `TABLEPROOF_VERIFY_URL=https://<venta>/verify` y `CHATBOT_PACK_MESSAGES` (lo definís vos).
- [hipótesis] cualquier hosting con docker y disco persistente sirve; no se eligió ni se probó ninguno.

## 6. anuncios (opcional, al final)

- gemini, para las imágenes: una clave de Google AI Studio. variables `GEMINI_API_KEY`, `GEMINI_IMAGE_MODEL` (el id que te muestre AI Studio). ver `docs/ads-verificado.md`.
- meta ads: página de facebook, cuenta publicitaria y un token con permiso de anuncios. variables `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_API_VERSION`.
- todo se crea en pausa; encender exige `--confirmo-gasto`.

## cómo saber qué falta

```
python -m engine.check ventures/chatbots-saas
```

lista lo que bloquea el arranque, incluidas las variables que faltan (solo los nombres, nunca los valores).
