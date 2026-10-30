# Roles y administración de plataforma

[Índice](README.md) · [Contrato completo](../../docs/REGLAS_Y_VISTAS_POR_ROL.md)

Los controladores usan RoleChecker, que consulta los roles actuales de PostgreSQL. HOST/VENUE administra recursos propios; ATTENDEE reserva, paga, consulta entradas y postula a grupos; ADMIN supervisa plataforma y gestiona asignaciones. Ningún permiso de HOST/ATTENDEE se deduce automáticamente de ADMIN.

app/admin/ separa DTO, controlador y servicio. /admin/overview agrega métricas reales; /admin/experiences consulta publicaciones y /users lista perfiles solo para ADMIN. PUT /admin/users/{id}/roles acepta uno o varios roles, serializa asignaciones, revalida ADMIN dentro de la transacción y protege contra quitarse ADMIN o dejar la plataforma sin un administrador activo.

POST /auth/mobile/login verifica credenciales, estado y ATTENDEE antes de emitir JWT. El login web conserva /auth/login. El autorregistro permite únicamente HOST/ATTENDEE. POST /users/me/role se conserva para clientes anteriores pero no concede ni retira roles.

## Propiedad y mutaciones

VenueService crea lugares con el usuario autenticado como propietario, lista únicamente los propios y permite configurar sus datos con PUT. ExperienceService exige el mismo propietario al asociar una experiencia a un lugar.

El DTO privado HostedExperienceDTO añade can_edit, can_delete y management_lock_reason. Editar/eliminar vuelve a calcular permisos bajo bloqueo de la experiencia. Retenciones vigentes, entradas pagadas y miembros de matching impiden cambios; cualquier historial de reserva impide el borrado. Se conserva la cancelación y conciliación de pagos como operaciones separadas.

Las modificaciones de lugar bloquean lugar → experiencias. La edición bloquea los lugares por UUID antes de bloquear la experiencia y comprueba que su lugar no haya cambiado mientras esperaba. Esto conserva el orden con configurar lugar y con crear reservas.

No hay columnas nuevas en este incremento. No reiniciar ni vaciar la base al actualizar los clientes.

## Primera cuenta administrativa

Crear o identificar la cuenta activa del propietario y ejecutar desde experiencia_back:

```sh
venv/bin/python scripts/grant_admin.py CORREO_DEL_PROPIETARIO
```

El comando usa las credenciales locales del operador y añade ADMIN sin borrar otros roles. No se ejecuta automáticamente al arrancar ni se eligió una cuenta durante la implementación. La administración posterior se realiza desde el panel web.

## Pruebas

test_role_workspaces.py verifica roles, emisión de sesión móvil, propiedad y protección de participantes. test_http_security.py comprueba rechazo por rol en rutas reales ASGI. test_postgres_integration.py añade CRUD de recursos propios, bloqueo tras reservas, carrera edición/reserva y persistencia de asignaciones en un esquema aislado.

En el entorno de implementación las conexiones psql siguen denegadas; estas pruebas de PostgreSQL quedan omitidas y deben ejecutarse en el host con acceso a la base.
