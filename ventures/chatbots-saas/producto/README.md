# producto: chatbot con la info del negocio

lo que se entrega al cliente que paga en `ventures/chatbots-saas`. el servidor de venta (`engine/app.py`) cobra y manda una clave; este servidor es donde esa clave se usa.

```
cliente paga ─► tableproof manda la clave TP-… y el link del panel (access_url)
panel (/) ─► con la clave carga la info de su negocio ─► recibe un <script> para pegar en su web
visitante de esa web ─► widget.js ─► POST /api/chat ─► Claude contesta solo con esa info
```

- `bot.py`: licencias, topes de uso, prompt y llamada al modelo.
- `server.py`: rutas (panel, demo, widget, chat). la lista está en su docstring.
- `static/`: `panel.html`, `demo.html`, `widget.js`.
- `demo_contenido.md`: negocio ficticio de la demo pública (`/demo`), que es el "valor gratis" del flow.

## correrlo

```
pip install -r requirements.txt -r ventures/chatbots-saas/producto/requirements.txt
python ventures/chatbots-saas/producto/server.py --port 8090
```

variables de entorno (en `.env`, ver `.env.example`): `ANTHROPIC_API_KEY`, `TABLEPROOF_VERIFY_URL` (el `/verify` del servidor de venta) y `CHATBOT_PACK_MESSAGES` (consultas que vale cada clave: lo define el dueño, sin valor por defecto). opcionales: `CHATBOT_MODEL` y los topes de `bot.DEFAULTS`.

## modelo de cobro: lo gratis es gratis y cada uno paga por lo que usa

- gratis: la demo pública. no tiene saldo, solo topes de uso.
- pago por uso, prepago: cada clave paga vale un paquete de `CHATBOT_PACK_MESSAGES` consultas. cada respuesta descuenta una del saldo del bot. sin saldo, el chat deja de contestar hasta que el cliente recarga en el panel con otra clave paga.
- una consulta que el modelo no pudo contestar no se descuenta. las frenadas por los topes tampoco.
- es un pago único por paquete, así que no hacen falta suscripciones de mercado pago.
- pendiente en el motor de venta: hoy admite un solo pedido por teléfono (`docs/mvp-punta-a-punta.md`), así que un cliente no puede comprar una recarga desde el mismo whatsapp. hay que levantar ese límite para que la recarga se pueda vender; no lo toqué.

`python ventures/chatbots-saas/producto/server.py uso` muestra mensajes y tokens por bot y por día: es el dato que falta para el riesgo 4 de `venture.md` (costo del modelo por conversación).

## qué hace cumplir

- sin clave válida no se guarda ni se contesta; una clave revocada deja de contestar a los 10 minutos como máximo.
- sin saldo no se llama al modelo; cada clave se acredita una sola vez.
- el bot contesta solo con la info cargada; lo que no está, dice que no lo sabe.
- no se guarda el texto de ninguna conversación, solo contadores.
- topes por bot y por día, por IP y por hora, y uno propio para la demo. pasado un tope no se llama al modelo.
- la info que excede el tamaño máximo se rechaza con un mensaje; no se recorta en silencio.

## estado

- [verificado 2026-10-14] tests sin red: `tests/test_chatbot_producto.py`, con modelo y licencias simulados.
- [hipótesis] la llamada real a la API de Claude y el aspecto del panel, la demo y el widget en un navegador: no se probaron. probarlos con una clave antes de publicar el link de la demo.
- el modelo por defecto es `claude-opus-5-5` con esfuerzo bajo. es el más capaz, no el más barato: cuál usar es una decisión de costo del dueño (`CHATBOT_MODEL`), y conviene tomarla con los números de `uso`.

## límites que conviene conocer

- el tope por IP usa la dirección de la conexión. detrás de un proxy propio, `CHATBOT_TRUST_FORWARDED=1`; sin proxy esa cabecera la puede falsificar cualquiera, por eso está apagada por defecto.
- el historial lo manda el navegador: un visitante puede alterar el suyo. no afecta a otros visitantes ni a la info del negocio.
- las instrucciones del prompt reducen, no eliminan, que el bot diga algo fuera de la info cargada. el widget y la oferta lo declaran ("puede equivocarse").
- una sola base sqlite: alcanza para empezar.
- revocar una clave que ya se acreditó como recarga no descuenta ese saldo (revocar la clave original sí apaga el bot).
- el saldo se cuenta en consultas, no en tokens: una info de negocio larga cuesta más por consulta y se cobra igual. `uso` muestra los tokens para ajustar el tamaño del paquete.
- un bot por clave; sin estadísticas para el cliente ni carga de archivos o de páginas web.
