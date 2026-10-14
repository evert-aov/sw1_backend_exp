# EXPERIENCIA — Backend API

Backend desarrollado en **Python 3.11+ con FastAPI**, utilizando una **Arquitectura en Capas** estricta y modularizada por paquetes de dominio, con persistencia relacional en **PostgreSQL** mediante **SQLAlchemy 2.0**.

---

## 🏛️ Arquitectura del Backend

El código fuente se encuentra en el paquete `app/` estructurado en 5 paquetes de negocio más un paquete transversal de configuración (`core`):

```text
app/
├── core/                                 # Configuración transversal
│   ├── config.py                         # Variables de entorno y settings (Pydantic)
│   ├── database.py                       # Engine, Base declarativa y get_db()
│   └── security.py                       # Hashing bcrypt y generación/validación JWT
│
├── auth/                                 # Paquete 1: Seguridad y Perfiles (CU-01, CU-02)
│   ├── entity/                           # Role, User, UserRole
│   ├── dto/                              # LoginDTO, RegisterDTO, ProfileDTO, ProfileUpdateDTO, TokenResponseDTO
│   ├── repository/                       # UserRepository, RoleRepository
│   ├── service/                          # AuthService, ProfileService
│   └── control/                          # auth_router (/api/auth), users_router (/api/users)
│
├── experience/                           # Paquete 2: Catálogo y Publicación (CU-03, CU-04, CU-05)
│   ├── entity/                           # Category, Venue, Experience
│   ├── dto/                              # CategoryDTO, VenueDTO, ExperienceCreateDTO, ExperienceFilterDTO, CatalogResponseDTO
│   ├── repository/                       # ExperienceRepository, CategoryRepository, VenueRepository
│   ├── service/                          # ExperienceService, CategoryService
│   └── control/                          # experience_router (/api/experiences), category_router (/api/categories)
│
├── booking/                              # Paquete 3: Reservas, Pagos y Suscripciones SaaS (CU-06, CU-14)
│   ├── entity/                           # Booking, Payment, Ticket, SaaSPlan, SaaSSubscription
│   ├── dto/                              # BookingCreateDTO, BookingResponseDTO, TicketDTO, CheckoutSessionDTO, SaaSPlanDTO
│   ├── repository/                       # BookingRepository, PaymentRepository, SubscriptionRepository
│   ├── service/                          # BookingService, StripeService
│   └── control/                          # booking_router (/api/bookings), payment_router (/api/payments), subscription_router (/api/subscriptions)
│
├── matching/                             # Paquete 4: Inteligencia de Demanda y Quórum (CU-07, CU-08)
│   ├── entity/                           # MatchingGroup, MatchingMember, UnmetDemand, SearchLog
│   ├── dto/                              # MatchingApplicationDTO, MatchingGroupResponseDTO, UnmetDemandInsightDTO, SuggestedExperienceDTO
│   ├── repository/                       # MatchingRepository, DemandRepository, SearchLogRepository
│   ├── service/                          # MatchingAlgorithmService, DemandPredictionService
│   └── control/                          # matching_router (/api/matching), demand_router (/api/demand)
│
└── live/                                 # Paquete 5: Visión Artificial y Asistencia en Vivo (CU-09..CU-13)
    ├── entity/                           # LiveSession, AudienceMetric (GDPR efímero), LiveSuggestion, Consent
    ├── dto/                              # LiveSessionCreateDTO, FramePayloadDTO, LiveMetricsDTO, ActionSuggestionDTO, PostEventReportDTO
    ├── repository/                       # LiveSessionRepository, AudienceMetricRepository, LiveSuggestionRepository, ConsentRepository
    ├── service/                          # ComputerVisionService, SmartHostService, PostEventReportService
    └── control/                          # live_router (/api/live - WebSockets), report_router (/api/reports)
```

---

## 📊 Tablas y Entidades Registradas (19 Tablas)

1. **`roles`**: Perfiles del sistema (ATTENDEE, HOST, VENUE, ADMIN).
2. **`users`**: Cuentas de usuario, credenciales e intereses temáticos.
3. **`user_roles`**: Tabla asociativa muchos a muchos.
4. **`categories`**: Categorías temáticas de experiencias.
5. **`venues`**: Espacios comerciales físicos geolocalizados por zona urbana.
6. **`experiences`**: Eventos con precio, cupo máximo, aforo mínimo (quórum) y modalidad.
7. **`bookings`**: Reservas de cupos con cálculo de comisiones escalonadas.
8. **`payments`**: Transacciones integradas con Stripe.
9. **`tickets`**: Entradas con código único y payload para código QR.
10. **`saas_plans`**: Planes de suscripción SaaS Pro.
11. **`saas_subscriptions`**: Suscripciones recurrentes gestionadas vía Stripe Billing.
12. **`matching_groups`**: Grupos dinámicos de participantes para alcanzar quórum.
13. **`matching_members`**: Asistentes postulados a un grupo de matching.
14. **`unmet_demands`**: Analítica de búsquedas urbanas sin oferta por zona.
15. **`search_logs`**: Registro histórico de búsquedas.
16. **`live_sessions`**: Sesiones de transmisión y telemetría en tiempo real.
17. **`audience_metrics`**: Agregación numérica de atención/energía en RAM (GDPR estricto sin fotos).
18. **`live_suggestions`**: Recomendaciones del Asistente MC (dinámicas) y DJ Virtual (BPM/música).
19. **`consents`**: Registro de consentimiento explícito GDPR para muestreo de video.

---

## 🚀 Puesta en Marcha para el Equipo

Sigue estos pasos en orden para clonar, levantar el backend y probar el avance del **Sprint 1**:

### 1. Requisitos Previos
- **Python 3.11+** o **3.12** instalado
- **PostgreSQL 15+** local (o una base de datos en la nube como **Neon Tech**)

### 2. Clonar rama y preparar Entorno Virtual
```bash
# Cambiarse a la rama del Sprint 1
git checkout feature/auth-sprint-1

# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows (PowerShell / CMD):
venv\Scripts\activate
# En Linux / macOS:
source venv/bin/activate

# Instalar dependencias del proyecto
pip install -r requirements.txt
```

### 3. Configuración de Variables de Entorno (`.env`)
Copia el archivo `.env.example` como `.env`:
```bash
# En Windows PowerShell:
Copy-Item .env.example .env
# En Linux / macOS / CMD:
cp .env.example .env
```
Edita `.env` según tu entorno:
- **Para PostgreSQL local:**
  ```env
  DB_HOST=localhost
  DB_PORT=5432
  DB_USER=postgres
  DB_PASS=12345
  DB_NAME=experiencia_db
  DB_SYNCHRONIZE=true
  ```
- **Para Neon Tech (o base de datos en la nube):**
  Puedes colocar directamente la variable `DATABASE_URL`:
  ```env
  DATABASE_URL=postgresql://neondb_owner:tu_password@ep-xyz.us-east-2.aws.neon.tech/experiencia_db?sslmode=require
  DB_SYNCHRONIZE=true
  ```

### 4. Inicializar Base de Datos y Poblar Datos Semilla (Seeder)
Ejecuta el script de seeding para sincronizar las tablas, crear los roles iniciales y generar los usuarios de prueba:
```bash
python seed.py
```

### 5. Ejecutar la Suite de Pruebas Automatizadas
Verifica que todos los endpoints funcionen correctamente con un solo comando:
```bash
python test_auth_endpoints.py
```
*Deberás ver: `[SUCCESS] ALL TESTS PASSED SUCCESSFULLY! SPRINT 1 IS 100% OPERATIONAL!`*

### 6. Levantar el Servidor de Desarrollo
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva disponible en:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## 👥 Usuarios de Prueba para el Equipo (Frontend & Móvil)

Todos los usuarios semilla tienen la **misma contraseña estándar**:  
🔑 **Contraseña:** `Password123!`

| Rol | Correo Electrónico | Contraseña | Uso sugerido |
| :--- | :--- | :--- | :--- |
| **HOST** | `host@experiencia.com` | `Password123!` | Probar creación y gestión de eventos (CU-03) |
| **ATTENDEE** | `attendee@experiencia.com` | `Password123!` | Probar exploración de catálogo y reservas (CU-04, CU-05) |
| **VENUE** | `venue@experiencia.com` | `Password123!` | Probar gestión de locales y demanda (CU-07) |
| **ADMIN** | `admin@experiencia.com` | `Password123!` | Administración general |

---

## 📱 Guía para Integración con Frontend (Angular) y Móvil (Flutter)

1. **Autenticación:** Enviar petición `POST` a `/api/auth/login` con:
   ```json
   {
     "email": "host@experiencia.com",
     "password": "Password123!"
   }
   ```
2. **Consumo de Endpoints Protegidos:** Adjuntar el token recibido en la cabecera HTTP:
   ```http
   Authorization: Bearer <access_token>
   ```
3. **Consultar Perfil del Usuario Logueado:** `GET /api/users/me`
4. **Actualizar Perfil e Intereses:** `PUT /api/users/me` con el JSON de campos a modificar.
