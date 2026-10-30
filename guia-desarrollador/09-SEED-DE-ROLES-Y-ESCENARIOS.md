# Seed de roles y escenarios de prueba

[Índice](README.md) · [Script](../scripts/seed_role_demo.py) · [Dataset](../app/core/demo_seed.py)

Este seed añade un conjunto independiente de datos ficticios para probar las reglas actuales del sprint 2. Usa PostgreSQL del .env del backend y no llama al seed antiguo ni a las funciones de reset.

Desde experiencia_back:

```sh
# Vista previa, sin conexión ni cambios:
venv/bin/python scripts/seed_role_demo.py --plan

# Cargar el conjunto roles-v2:
venv/bin/python scripts/seed_role_demo.py

# Crear otro conjunto independiente, con nuevos correos e identificadores:
venv/bin/python scripts/seed_role_demo.py --dataset roles-v3
```

La base debe tener el esquema vigente. Si faltan tablas o columnas, ejecutar scripts/migrate_database.py antes de cargar el seed. No es necesario vaciarla.

## Cuentas del conjunto predeterminado

Contraseña de demostración de las cuentas nuevas: **DemoRoles2026!**. Se puede proporcionar otra mediante la variable de proceso DEMO_SEED_PASSWORD; su valor no se imprime. Repetir el seed conserva las contraseñas existentes.

| Correo | Roles | Inicio web | Acceso móvil |
| --- | --- | --- | --- |
| admin.roles-v2@example.com | ADMIN | /admin | No |
| host-cultura.roles-v2@example.com | HOST | /host | No |
| host-talleres.roles-v2@example.com | HOST | /host | No |
| ana.roles-v2@example.com | ATTENDEE | /catalog | Sí |
| luis.roles-v2@example.com | ATTENDEE | /catalog | Sí |
| dual.roles-v2@example.com | HOST + ATTENDEE | /host | Sí |

Los correos, nombres, direcciones y coordenadas son datos de demostración. Los tres lugares pertenecen respectivamente a los dos HOST y a la cuenta multirrol; cada experiencia física utiliza un lugar de su anfitrión.

## Escenarios

Se crean cuatro categorías, tres lugares y diez experiencias con fechas relativas a la primera ejecución:

| Experiencia | Caso que permite probar |
| --- | --- |
| Taller de acuarela | Editar/eliminar antes de recibir participantes |
| Encuentro gratuito de café | Dos reservas gratuitas alcanzan quórum y emiten dos entradas |
| Laboratorio creativo | Una reserva gratuita de dos entradas ocupa todo el aforo |
| Cata de café | Reserva pendiente de 100 BOB, con la retención normal configurada |
| Ruta del café | Tres miembros alcanzan el interés del grupo; aún deben reservar y pagar |
| Fotografía móvil | Experiencia virtual editable |
| Prototipado de ideas | Modalidad híbrida |
| Dibujo al aire libre | Publicación de la cuenta multirrol |
| Taller cancelado | Estado cancelado sin reservas |
| Encuentro finalizado | Estado histórico del panel del anfitrión, sin reservas |

Las cuatro entradas gratuitas son emitidas por BookingService con sus firmas y reservas reales. MatchingAlgorithmService forma el grupo y ambos servicios generan avisos. No se crean sesiones, cobros ni reembolsos falsos de Stripe; la reserva de pago queda pendiente y permite continuar el checkout manualmente. Para comprobar ingresos monetarios se debe completar una compra de prueba mediante Stripe.

También se insertan doce observaciones sintéticas de demanda sin oferta en Plan 3000 y Pampa de la Isla, identificadas con el prefijo Demo y search_filters.source=demo-seed. Son ejemplos de filtros/presupuestos, no tráfico real de usuarios.

## Repetición y transacciones

Los UUID y las claves de idempotencia son estables por nombre de dataset. Repetirlo conserva perfiles, contraseñas, fechas, cambios de experiencias y reservas existentes. Las retenciones no se renuevan al repetir. Si una cuenta de ese conjunto cambió de roles o propietario, se informa el conflicto y se puede elegir un dataset nuevo, conservando esos cambios.

Un correo ya existente con otro UUID nunca se adopta ni recibe ADMIN. El seed solo asigna roles al crear sus propias cuentas nuevas.

La carga usa una transacción PostgreSQL externa y savepoints: los commits internos de los servicios no confirman el conjunto completo. Ante un error se revierte la carga del conjunto. Esta composición sigue el [contrato de transacciones externas de SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites). Las pruebas de rollback, repetición e identidad están añadidas para ejecutarse con PostgreSQL.

En el entorno de implementación no se pudo cargar la base: psql sale con código 2 y la creación de sockets falla con PermissionError/Operation not permitted antes de autenticar. Existe una [vista previa del dataset](../../docs/evidencias/seed_roles_v2_plan.json). Ejecutar el comando desde la terminal del host para cargarlo.
