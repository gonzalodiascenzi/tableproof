# Anuncios (Gemini + Meta Ads): qué se verificó y qué sigue como hipótesis (2026-10-09)

Regla de la casa: [verificado] con fuente y fecha, o [hipótesis]. Las páginas se leyeron con un resumidor automático de páginas, no a mano: contrastar con la página antes de gastar. Por eso `engine/ads.py` crea TODO en pausa y no enciende nada sin `--confirmo-gasto`.

## [verificado]
- Meta, crear un conjunto de anuncios (`POST /act_{id}/adsets`): `name` es obligatorio; hace falta `campaign_id` (o `campaign_spec`); `daily_budget` o `lifetime_budget` debe ser mayor que 0 (entero en la moneda de la cuenta); `daily_budget` solo vale para conjuntos de más de 24 h; en `targeting`, `countries` es obligatorio. Fuente: [referencia de ad sets](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/adsets) (leída el 2026-10-09).
- Meta, el ejemplo de tráfico de esa página usa `billing_event=LINK_CLICKS` y `optimization_goal=LINK_CLICKS`. Misma fuente. (Este motor usa otros valores porque el objetivo es click-to-whatsapp: ver hipótesis.)
- Meta, versión más reciente que menciona esa página: v25.0. El código NO la tiene escrita: sale de `META_API_VERSION`.
- Gemini, la página de generación de imágenes ([ai.google.dev](https://ai.google.dev/gemini-api/docs/image-generation), leída el 2026-10-09 con resumidor) recomienda el modelo `gemini-nano-banana-2.1` y muestra un pedido a `POST /v1beta/interactions` con cabecera `x-goog-api-key` y `response_format` (`type`, `mime_type`, `aspect_ratio`, `image_size`); la imagen vuelve en base64 en `output_image.data`. Esa página no documentaba `generateContent`.

## [hipótesis] (implementado así y a contrastar con una cuenta real)
- El id del modelo de imágenes: no está escrito en el código; sale de `GEMINI_IMAGE_MODEL`. Usá el que te muestre Google AI Studio.
- Qué forma de pedido acepta tu cuenta: `generate_content` (por defecto: `POST /v1beta/models/{modelo}:generateContent`, con `responseModalities: ["IMAGE"]` y la imagen en `inlineData`) o `interactions` (la de la página de arriba). Se elige con `GEMINI_IMAGE_API`. Si una falla, probá la otra.
- Los campos de click-to-whatsapp: campaña con objetivo `OUTCOME_ENGAGEMENT`; conjunto con `destination_type=WHATSAPP`, `optimization_goal=CONVERSATIONS`, `billing_event=IMPRESSIONS`, `promoted_object` con `page_id` y `whatsapp_phone_number`; creatividad con `call_to_action` de tipo `WHATSAPP_MESSAGE` y `app_destination=WHATSAPP`, y el link `https://api.whatsapp.com/send?phone=...&text=...`. Salen de conocimiento previo, no de una página leída hoy.
- Subida de imagen con el campo `bytes` (base64) de `/adimages` y respuesta con `images.<nombre>.hash`.
- Que `daily_budget` vaya en la unidad mínima de la moneda (centavos): el código multiplica por 100.
- Parámetros que la API pueda exigir hoy y que acá no están (por ejemplo, algún campo sobre presupuesto compartido entre conjuntos): si Meta rechaza un pedido, el error de la API aparece tal cual (sin el token) y se agrega el campo en `build_plan`.
- Que Meta acepte imágenes generadas por IA sin etiquetarlas, y las políticas de anuncios sobre el producto que vendas: releer antes de encender. La guarda de `engine/ads.py` solo frena frases de promesa de ingresos o de "sin riesgo"; no reemplaza leer la política.
