# mvp de venta punta a punta

anuncio con imagen de gemini en meta ads → whatsapp con respondedor → link de pago de mercado pago → entrega automática (clave de acceso o descarga firmada). todo se arma desde `ventures/<slug>/`.

```
anuncio (pausado hasta que lo enciendas)
   └─ click a whatsapp ─► engine/app.py  POST /webhook ─► respondedor (flow.yaml)
                                                             └─ {pay_link} ─► link de mercado pago
cliente paga ─► POST /mp (firma + consulta a la API) ─► entrega automática por whatsapp
                                                         ├─ access:   clave TP-XXXX-…  (+ GET /verify?key=)
                                                         └─ download: link firmado GET /d/<token>
```

## pasos

1. `python -m engine.scaffold <id> --source <data/ingredients.json de seedproof o su URL> --kind access` (o `download`). crea `ventures/<slug>/` desde `ventures/_plantilla/`.
2. completá `venture.yaml` y `flow.yaml`. todo lo que diga `[completar ...]` bloquea el arranque. **lo que decidís vos y no tiene valor por defecto:** `price_ars`, `ads.daily_budget`, `ads.countries`. para `download`, poné el archivo en `ventures/<slug>/entrega/` (no se commitea).
3. copiá `.env.example` a `.env` y completá las claves (solo nombres en el repo; los valores no se commitean).
4. `python -m engine.check ventures/<slug>`: te dice qué falta (sin red, nunca imprime valores).
5. anuncios (opcionales): `python -m engine.ads plan ventures/<slug>` (sin claves), `images` (gemini), `create` (queda TODO en pausa). revisá la campaña en el administrador de anuncios.
6. `python -m engine.app ventures/<slug>` (o el Dockerfile). configurá en cada panel la url pública: `https://<tu dominio>/webhook` en whatsapp y `https://<tu dominio>/mp` en mercado pago (evento Pagos).
7. probá de punta a punta con credenciales de prueba y un número de prueba (ver `docs/whatsapp-local.md`, `docs/mercadopago-verificado.md`).
8. recién ahí: `python -m engine.ads activate ventures/<slug> --confirmo-gasto`.

## qué te toca a vos (no se puede hacer desde el código)

- app de meta, página, cuenta publicitaria y número de whatsapp business; el token de acceso con permisos de anuncios (`ads_management`) y la versión de la api vigente.
- cuenta y credenciales de mercado pago; el secreto del webhook.
- clave de gemini y el id del modelo de imágenes que te muestre google ai studio.
- un dominio https público para el servidor, con la base sqlite en un disco que no se borre.
- las plantillas de whatsapp aprobadas (`python -m engine.templates <flow.yaml>`).
- el archivo a entregar, si es de descarga. un `.exe` sin firmar suele disparar avisos de windows: es un tema del producto, no del servidor.

## decisión pendiente tuya: cobrar plata real

`engine/payments.py` solo opera en modo de prueba a propósito (exige `MP_MODE=test` y rechaza notificaciones con `live_mode` verdadero). **No la modifiqué.** para cobrar de verdad hay que levantar esa guardia, y conviene hacerlo recién después de probar con el sandbox, porque tres cosas del cobro siguen como hipótesis sin probar contra la API real (ver `docs/mercadopago-verificado.md`): la creación de la preferencia, el valor `approved` y el formato de la firma. decime si querés que la levante (con `MP_MODE=live` explícito y que el handler solo acepte notificaciones del modo elegido) y la cambio con sus tests.

## límites que conviene conocer

- un pedido por teléfono: quien ya pagó recibe `already_paid_message`, no un segundo link. excepción: con `repeat_purchase: true` en venture.yaml (productos que se recargan), el mismo teléfono puede comprar otra vez cuando su pedido anterior ya fue entregado.
- si el cliente paga pasadas 24 h desde su último mensaje, el envío de texto libre puede ser rechazado por whatsapp: la entrega falla, se reintenta, queda `entrega_fallida` y te llega un aviso (`avisos.log`). [hipótesis] sobre la regla exacta de whatsapp: contrastar.
- reembolsos y contracargos no revocan nada solos: te avisan. para quitar un acceso: `python -m engine.delivery revoke <archivo.sqlite> <clave>`.
- `/verify` no limita intentos; ponele un límite de tasa adelante si lo exponés.
- una sola conexión sqlite con un candado: alcanza para empezar, no para mucho tráfico.
- el texto de los anuncios pasa por una guarda de promesas (ingresos garantizados, "sin riesgo", etc.). no reemplaza leer la política de anuncios de meta ni evitar prometer resultados en el producto mismo.
