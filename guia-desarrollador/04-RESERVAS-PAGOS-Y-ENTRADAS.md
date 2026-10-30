# Reservas, pagos y entradas — sprint 2

[Índice](README.md) · [Reservas](../app/booking/service/booking_service.py) · [Stripe](../app/booking/service/stripe_service.py) · [Adaptador](../app/booking/service/stripe_gateway.py)

CU-05 cubre HU-06/HU-07/HU-12. Los servicios y los clientes están implementados. La aceptación de compras reales sigue pendiente de PostgreSQL accesible, claves Stripe y una demostración con webhook auténtico.

## Contratos

Todas las rutas llevan prefijo /api. Salvo webhook, requieren JWT.

| Método y ruta | Resultado |
| --- | --- |
| POST /bookings | experience_id, quantity 1–20 e Idempotency-Key: crea retención o confirma una reserva gratuita |
| GET /bookings/my-tickets | Historial propio, estado del evento, dinero, devolución y tickets anidados |
| GET /bookings/{id} | Reserva propia; no acepta estados enviados por el cliente |
| POST /bookings/{id}/cancel | Cancela una retención pendiente |
| POST /payments/checkout/{id} | Inicia o recupera la sesión Stripe propia |
| POST /payments/status/{id} | Consulta Stripe desde el servidor y concilia la reserva propia |
| POST /payments/webhook | Cuerpo crudo y Stripe-Signature; deduplicación por ID de evento |
| POST /payments/refund/{id} | Devolución completa propia antes del evento y sin entradas utilizadas |
| GET /bookings/tickets/{id}/qr | SVG autorizado del QR firmado, con caché privada deshabilitada |
| GET /bookings/tickets/verify/{code} | Consulta autorizada sin consumir entrada |
| POST /bookings/tickets/{id}/check-in | Consume una entrada exclusivamente para el anfitrión propietario |
| POST /bookings/tickets/check-in | Acepta code con lectura firmada del QR o código legible |
| GET /bookings/host-income | Bruto/comisión/neto, devuelto y devoluciones pendientes de eventos propios, por moneda |

401 indica falta de sesión; 403 recurso ajeno; 404 recurso inexistente; 409 estado/cupo/importe incompatible; 422 entrada inválida o solicitud rechazada por Stripe; 502 fallo de conexión/proveedor; 503 clave, permisos, moneda, URL o dependencia no configurados correctamente.

## Dinero, capacidad e idempotencia

Numeric/Decimal conserva precio, tasa, bruto, comisión y neto congelados. El servidor convierte a unidades menores al llamar a Stripe y admite BOB, USD y EUR. No hay conversión implícita. El neto es un desglose contable; no implementa transferencias bancarias al anfitrión.

La retención dura BOOKING_HOLD_MINUTES, 15 por defecto, limitada por el inicio del evento. reserved_slots cuenta cupos confirmados; los pendientes vigentes se agregan por separado. La clave se conserva durante los reintentos; reutilizarla con otra cantidad/evento devuelve 409. Los clientes no envían importes ni medios de pago ficticios.

El orden de bloqueos es cuenta → experiencia → reserva → pago/entrada. La cuenta usa FOR NO KEY UPDATE: serializa reservas y permite los KEY SHARE requeridos por las FK de los avisos. Los repositorios hacen flush y el servicio controla commits.

El intento de checkout y sus parámetros se guardan antes de llamar a Stripe. Una respuesta perdida se recupera usando los mismos parámetros y la misma clave remota. Solo se redirige a https://checkout.stripe.com. El retorno del navegador consulta el backend; no demuestra un pago.

Checkout usa métodos dinámicos habilitados en el Dashboard de Stripe. No envía payment_method_types ni automatic_payment_methods al crear la sesión. Si un intento antiguo guardó payment_method_types y recibió InvalidRequestError para ese campo, el siguiente intento retira únicamente ese campo y guarda checkout_params_version=2 antes de llamar al proveedor. Conserva monto, moneda, reserva y clave remota. Sesiones ya creadas e intentos con resultado incierto conservan sus parámetros originales.

### Diagnóstico de un checkout fallido

El backend clasifica la excepción del SDK y muestra una causa accionable en la respuesta. La consola registra una línea Stripe checkout failed con category, code, param, request_id y mensaje acotado/redactado. No imprime cuerpos ni cabeceras completos. La referencia req_ permite localizar la operación en Stripe Workbench.

La misma información queda en Payment.payment_metadata.last_checkout_error, manteniendo la reserva y el intento PENDING. Al reintentar con éxito se limpia ese diagnóstico. Los fallos de conexión no cambian la clave ni checkout_params; la adaptación del campo retirado solo procede con el rechazo de validación registrado y sin sesión remota persistida.

Si solo se dispone del antiguo 502 genérico, no se puede concluir si la causa fue clave, conexión, importe mínimo o configuración de cuenta. Reintentar una retención vigente con el backend actualizado y revisar la línea de diagnóstico. Si venció, crear otra reserva. La creación de sesión no usa el secreto de firma del webhook; ese secreto se comprueba al recibir las confirmaciones.

## Webhooks y recuperación

Configurar eventos snapshot checkout.session.completed, checkout.session.async_payment_succeeded, checkout.session.expired y checkout.session.async_payment_failed.

La firma se comprueba con el cuerpo crudo. stripe_events guarda ID, tipo, objeto y resultado, sin copiar todo el cuerpo. Pago, cupos, entradas, avisos y registro del evento se confirman en una transacción. Duplicados no repiten efectos; una expiración/fallo tardíos no revierten un pago ya confirmado. Una sesión propia aún no persistida devuelve 503 para que Stripe reintente.

La cantidad de interesados de matching no confirma un evento. El quórum usa cupos pagados o gratuitos confirmados. Cada cupo emite un ticket firmado. El ingreso requiere evento CONFIRMED, anfitrión propietario y entrada sin usar/devolución solicitada.

Stripe impone un mínimo de 30 minutos para expires_at de Checkout; la retención local de 15 minutos se mantiene. No se fuerza una expiración remota incompatible: el conciliador cierra sesiones abiertas sin retención y un cobro tardío se registra para devolución, sin ocupar cupos ni emitir entradas.

## Devoluciones y cancelación

refund_requested se persiste antes de llamar al proveedor. La misma clave remota protege los reintentos. Un refund pending deja el dinero en PAID y bloquea el uso de las entradas. Solo succeeded cambia a REFUNDED y libera cupos una vez. failed/canceled requiere revisión operativa y permanece visible en el historial.

Cancelar un evento invalida retenciones y deja solicitudes durables de devolución para cobros Stripe conciliados. Las reservas gratuitas se invalidan localmente. Cobros históricos sin Payment verificado impiden la cancelación automática. El plazo para cancelar por falta de quórum sigue pendiente de decisión; no se ha activado esa cancelación por reloj.

Programar cada minuto, con el mismo entorno del backend:

```sh
venv/bin/python scripts/expire_bookings.py
venv/bin/python scripts/reconcile_payments.py
venv/bin/python scripts/expire_matching_groups.py
```

El conciliador procesa lotes de hasta 500 pagos pendientes/devoluciones no terminales. No instalar estos comandos como procesos duplicados por cada cliente.

## Preparación y demostración

Instalar requirements.txt, configurar STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET y FRONTEND_URL en .env. FRONTEND_URL vale http://localhost:3000 por defecto y determina URLs de retorno del servidor. STRIPE_PUBLISHABLE_KEY puede guardarse en el mismo entorno, pero Hosted Checkout no la utiliza: el navegador recibe la URL de la sesión creada por el backend. Nunca poner la clave secreta en Angular/Flutter.

```sh
uv pip install --python venv/bin/python -r requirements.txt
venv/bin/python scripts/check_database.py
venv/bin/python scripts/check_stripe.py
venv/bin/python scripts/migrate_database.py
npx stripe listen \
  --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.expired,checkout.session.async_payment_failed \
  --forward-to http://localhost:8000/api/payments/webhook
```

El secreto de Stripe CLI debe configurarse en .env y reiniciar la API. Usar claves y tarjetas de prueba del proveedor, nunca publicar sus valores. Aplicar todas las revisiones hasta head; DB_SYNCHRONIZE=true también las aplica al arrancar.

La CLI usada mediante npx exige seleccionar los eventos: omitir --events produce «must specify events to forward». Mantener el listener abierto mientras se prueban pagos. Si solicita autenticación, completar npx stripe login en la misma cuenta de prueba. El backend recibe eventos snapshot; configurar en STRIPE_WEBHOOK_SECRET el whsec_ mostrado por este listener.

check_stripe.py consulta la cuenta para comprobar autenticación sin crear recursos ni cobros y sin imprimir claves/saldos. También indica si falta el secreto del webhook. Un fallo de conexión no demuestra que una clave esté revocada; los secretos de firma de CLI y del endpoint del Dashboard son distintos y se usa el correspondiente a quien entrega el evento.

Referencias primarias: [Checkout](https://docs.stripe.com/api/checkout/sessions/create), [métodos dinámicos](https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods), [idempotencia y errores de validación](https://docs.stripe.com/api/idempotent_requests), [firma y deduplicación de webhooks](https://docs.stripe.com/webhooks), [devoluciones](https://docs.stripe.com/api/refunds/create). Ver [avance y límites de verificación](../../docs/AVANCE_SPRINT_2.md).
