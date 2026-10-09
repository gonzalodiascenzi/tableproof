# auditoría adversarial del motor (prompt 10)

estado: informe. no se modificó código. espera ok del dueño.
método: reproducciones con un script fuera del repo + búsqueda de secretos en el historial git (limpio: solo constantes falsas de tests).

| id | severidad | hallazgo |
|----|-----------|----------|
| H1 | alta | un "baja" que llega tarde (ts anterior al último mensaje procesado) se ignora y no registra el opt-out |
| H4 | media-alta | el handoff a humano y la entrega fallida no avisan al dueño (`_notifier` opcional y sin cablear) |
| H2 | media | el texto del cliente se guarda tal cual en `events` (ej. CBU/DNI) |
| H3 | media | falsos positivos de palabras clave: "¿me baja el precio?", "no quiero que me den de baja", "stop-motion" |
| H5 | media | se pierde el mensaje si falla el procesamiento después de marcarlo en `processed` (at-most-once; el reintento de Meta se salta) |
| H6 | baja (solo servidor dev) | `Content-Length: -1` deja colgado el servidor; servidor single-thread sensible a clientes lentos |

## H1 — opt-out tardío ignorado (alta)
- reproducir: procesar un mensaje con ts=100, luego un "baja" con ts=90. resultado: `opt_out_at: None`, se le sigue escribiendo.
- por qué importa: contradice la regla "baja/stop = inmediato". es el riesgo regulatorio y de reputación más grande.
- fix propuesto: la regla de orden por ts no aplica a palabras de baja; procesarlas siempre, y registrar opt-out aunque el mensaje sea viejo.

## H4 — sin aviso al dueño (media-alta)
- reproducir: mensaje "quiero hablar con una persona" → estado handoff, nadie es notificado. `deliver_with_retries` solo notifica si `cfg["_notifier"]` existe y nadie lo setea.
- fix propuesto: interfaz `Notifier` obligatoria en el arranque (con implementación por defecto que escribe a archivo/log visible + canal configurable); fallar al iniciar si falta.

## H2 — datos sensibles en `events` (media)
- reproducir: enviar "mi cbu es …" / "mi dni …"; queda en la tabla.
- fix propuesto: guardar solo tipo de evento y metadatos por defecto; texto del cliente opcional, truncado y con enmascarado de secuencias numéricas largas; retención con borrado.

## H3 — falsos positivos de keywords (media)
- reproducir: "¿me baja el precio?", "no quiero que me den de baja", "stop-motion video" → opt-out. "una persona me estafó…" → handoff.
- fix propuesto: baja solo si el mensaje normalizado es (casi) exactamente la palabra clave; para las ambiguas, responder confirmando ("¿querés que te demos de baja? respondé BAJA"). tests con estos casos.

## H5 — pérdida por fallo tras marcar procesado (media)
- reproducir: forzar excepción después de insertar en `processed`; el reintento de Meta se descarta como duplicado.
- fix propuesto: marcar `processed` en la misma transacción que el cambio de estado y el registro del envío; si falla, rollback y que el reintento reprocese.

## H6 — servidor dev (baja)
- reproducir: `Content-Length: -1` → sin respuesta en 3 s.
- fix propuesto: validar 0 ≤ largo ≤ tope, timeout de socket, `ThreadingHTTPServer`. recordatorio: no es para producción; usar un servidor real detrás de https.

## otros puntos (sin reproducción dura)
- firma de Mercado Pago: sin tolerancia de timestamp y body sin firmar; mitigado porque se consulta el pago a la API y hay idempotencia. si el manifest [hipótesis] está mal, todas las notificaciones reales fallan cerradas con 401 (seguro, pero rompe el cobro). contrastar contra la doc oficial antes de producción.
- firma de WhatsApp: asumido sobre bytes crudos [hipótesis]; versión de API por env.
- `deliver_with_retries` exige entregadores idempotentes; no hay reintento automático posterior de entregas fallidas.
- dos pagos aprobados distintos para un mismo pedido pueden competir y entregar doble con servidor multihilo.
- reembolsos/contracargos después de entregar: sin manejo.
- tras una baja, el usuario no puede reactivarse sin opt-in explícito registrado por el dueño.
- el motor no valida que los textos del flow eviten pedir datos sensibles.
- no hay LLM todavía: la inyección de prompt hoy se limita al matcheo de keywords. cualquier paso con LLM futuro debe aislarse (sin herramientas, salida validada contra estados permitidos).

## orden sugerido de corrección
H1 → H4 → H5 → H3 → H2 → H6, luego contrastar hipótesis de firmas.
