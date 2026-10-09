> **archivado (2026-10-08).** no cumple el criterio actual de seedproof (criteria_version 2). motivo, con las líneas de este mismo archivo:
> - F2, entrega que requiere una persona: el paso 3 dice "veredicto en minutos, revisado por vos".
> - F3, horas humanas por pedido mayores a 0: cada consulta, incluida la gratis, pasa por una persona.
> - cobro: el abono va con link de mercado pago, pero el archivo no define que el acceso se active por la notificación de pago confirmada (sin dato).
> - tensión con la cláusula 4.7 (riesgo 1 abajo): quitar la revisión humana para cumplir F2 y F3 acerca a la IA a ser la funcionalidad principal.
> se puede reabrir si la revisión humana se reemplaza sin que la IA sea el producto principal. el contenido de abajo es el original, sin cambios.

# scamproof

primer caso del framework. estado: flujo escrito, sin test lanzado.

## 0. ficha

- nombre: scamproof
- fecha de inicio: 2026-10-08
- estado: flujo escrito
- dueño de la decisión de corte: gonzalo

## 1. hipótesis falsable

- [hipótesis] 20 comercios chicos argentinos que venden por redes pagan un abono mensual chico por revisar comprobantes, links y números sospechosos, y por blindar su whatsapp business y su mercado pago.
- por qué creo que es cierta: [hipótesis] el dolor (comprobantes truchos, phishing con links falsos de mercado pago, cuentas hackeadas) es frecuente y concreto. no hay dato propio todavía. el test existe para medirlo.

## 2. oferta en una línea

"mandame la captura, el link o el número que te da mala espina y en minutos te digo qué señales tiene."

- gratis: una consulta, con veredicto de señales y qué hacer
- pago: abono mensual para comercios, con consultas ilimitadas y checklist de blindaje (2fa, avisos de phishing, configuración de whatsapp business y mercado pago)
- precio del abono: [hipótesis], a definir en el test (no se fija sin datos)
- límite declarado de entrada: una captura no prueba que la plata llegó. el veredicto detecta señales de fraude. la confirmación real del pago se hace siempre en la app del banco o de mercado pago.

## 3. flujo de whatsapp

1. **entrada**: anuncio click-to-whatsapp. mensaje pre-armado: "hola, quiero revisar algo sospechoso".
2. **saludo y calificación**: el respondedor se presenta, avisa que es un asistente automático con persona detrás, y pregunta: ¿qué vendés?, ¿qué te pasó o qué querés revisar?, ¿cuántas ventas hacés por semana?
3. **valor gratis**: pide la captura, el link o el número. instrucción antes de enviar: tapá o recortá CBU/CVU, CUIT, DNI y cualquier dato de cuenta; solo necesito monto, fecha, hora y número de operación. veredicto en minutos, revisado por vos.
4. **oferta**: si pidió una segunda consulta o dijo que vende seguido, ofrecer el abono con link de pago de mercado pago.
5. **seguimiento**: mensaje a las 24 h dentro de la ventana de atención; después de eso, solo con plantilla aprobada y solo a quien dio opt-in.
6. **salida a humano**: en cualquier paso, escribiendo "persona" o por el número/correo del perfil.

## 4. cumplimiento (política de meta, verificado 2026-10-08)

fuentes: política de mensajes de whatsapp business (es-la) y condiciones de meta para la plataforma de whatsapp business, ambas con última actualización 2026-09-23.

[verificado] qué dicen:
- se puede usar automatización al responder dentro de la ventana de 24 h, siempre que haya salidas claras y rápidas a una persona (chat humano, teléfono, correo, web, formulario).
- los mensajes iniciados por la empresa solo pueden ir con plantillas aprobadas; fuera de las 24 h, solo plantillas.
- solo se puede contactar a quien dio su número y aceptó recibir mensajes.
- no se debe compartir ni pedir números completos de cuentas bancarias, tarjetas, documentos de identidad ni otros identificadores sensibles.
- no se puede suplantar ni engañar sobre la naturaleza del negocio; también se prohíben modelos de negocio que meta considere fraudulentos o engañosos, a su exclusivo criterio.
- cláusula 4.7: los proveedores de IA (modelos, plataformas generativas, asistentes de uso general) tienen prohibido usar la plataforma cuando la IA es la funcionalidad principal que se ofrece, según lo determine meta a su criterio. los datos de la plataforma no pueden usarse para crear, entrenar ni mejorar modelos de IA (se permite ajustar un modelo para uso exclusivo propio).

[inferencia mía, no verificada con meta] qué implica para scamproof:
- el producto principal es un servicio antifraude con revisión humana; la IA es una herramienta interna. conviene que el posicionamiento, el perfil y los mensajes digan eso, y que sea cierto.
- meta decide a su criterio si la IA es "principal" o "auxiliar". no hay garantía de que scamproof pase. es un riesgo que no se elimina, se reduce.
- el flujo choca con la regla de identificadores sensibles: los comprobantes de transferencia suelen mostrar CBU/CVU, CUIT o nombre completo. por eso el paso 3 pide tapar esos datos. si la gente igual los manda, hay que decidir qué hacer con esas capturas (no reenviarlas, no guardarlas más de lo necesario).
- si el análisis usa un modelo de IA vía API, hay que confirmar con los términos del proveedor del modelo cómo trata los datos, y no usar esos chats para entrenar nada.

[no leído] existe un servicio opcional de meta, los "Business Agent", con condiciones propias. las condiciones lo nombran; no leí sus términos.

pendiente de revisión legal: responsabilidad si un veredicto falla. conviene un aviso de alcance redactado por alguien que sepa, y la parte fiscal (monotributo, facturación) la tiene que ver un contador. no lo investigué.

## 5. test chico

- presupuesto máximo: a definir por gonzalo
- duración: [hipótesis] 7 a 14 días
- público: comercios chicos y vendedores de redes en argentina
- una conversación cuenta cuando la persona contesta la primera pregunta del respondedor

## 6. tres números

| métrica | cómo se mide | valor |
|---|---|---|
| costo por conversación iniciada | gasto en anuncios / conversaciones | sin dato |
| % que usa la consulta gratis | usaron gratis / conversaciones | sin dato |
| % que paga el abono | pagaron / usaron gratis | sin dato |

## 7. criterio de corte y de escala

los umbrales los pone gonzalo antes de gastar un peso. no los invento acá, porque cualquier número sería una hipótesis más.

- se mata si: 
- se corrige una vez si: 
- se escala si: 

## 8. bitácora

2026-10-08 | se eligió scamproof como primer caso y se verificó la política de meta | ver sección 4 | pendiente definir presupuesto y umbrales

## 9. riesgos abiertos

1. meta puede considerar que la IA es la funcionalidad principal (cláusula 4.7). dueño: gonzalo. revisar antes de lanzar.
2. identificadores sensibles en los comprobantes que manden los clientes. dueño: gonzalo. definir antes de lanzar.
3. responsabilidad por veredictos equivocados. dueño: gonzalo, con asesoría legal.
4. fiscal (monotributo, facturación). dueño: gonzalo, con contador.
5. precio del abono sin ningún dato. se define en el test.
