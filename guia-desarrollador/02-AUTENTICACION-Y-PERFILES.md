# Autenticación y perfiles

[Índice](README.md) · [Controlador](../app/auth/control/auth_controller.py) · [Seguridad](../app/core/security.py)

CU-01 reúne registro, login, logout y refresh (HU-01/HU-02). Perfil es CU-02 (HU-03). Las etiquetas públicas de los controladores usan esta numeración; algunos comentarios históricos todavía conservan números anteriores.

| Ruta | Contrato |
| --- | --- |
| `POST /api/auth/register` | RegisterDTO → ProfileDTO; solo ATTENDEE/HOST, sin token |
| `POST /api/auth/login` | LoginDTO → TokenResponseDTO |
| `POST /api/auth/logout` | JWT activo → huella revocada persistida |
| `POST /api/auth/refresh` | JWT válido/no revocado y usuario activo → nuevo token |
| `GET /api/users/me` | Perfil del sujeto autenticado |
| `PUT /api/users/me` | ProfileUpdateDTO, sin campos administrativos |
| `PATCH /api/users/me/preferences` | Intereses, biografía y avatar por URL |
| `POST /api/users/me/role` | Compatibilidad; no concede ni retira roles |

AuthService normaliza correo, valida rol antes de consultar SQL, calcula bcrypt y confirma usuario/rol en una transacción. Los repositorios permiten flush sin commit para evitar cuentas sin rol ante un fallo; la unicidad del rol resuelve altas concurrentes mediante upsert PostgreSQL.

`get_current_active_user` valida firma/expiración, consulta revocación y recupera la cuenta activa. RoleChecker aplica permisos del servidor. RevokedToken conserva SHA-256 del JWT y vencimiento, nunca el token original: logout se comparte entre procesos y sobrevive al reinicio. Aplicar la migración `20261025_01` antes de usar autenticación con esta versión. Las revocaciones vencidas pueden depurarse después de su expiración.

Los roles se asignan desde /admin/users/{id}/roles por ADMIN. El endpoint público anterior no cambia asignaciones. POST /auth/mobile/login exige ATTENDEE antes de emitir un token; ADMIN no implica HOST ni ATTENDEE. Ver [administración y roles](08-ROLES-Y-ADMINISTRACION.md).

Web y móvil solicitan logout remoto y limpian su estado local aun si falla la conexión. Sin confirmación remota, el JWT podría seguir válido hasta su expiración; la limpieza local no demuestra revocación.

Verificar integración real, JWT caducado/revocado, usuarios inactivos, 401/403 y reversión de un registro fallido. La prueba PostgreSQL preparada cubre revocación entre sesiones y registro atómico, pero permanece omitida mientras el entorno deniegue sockets.
