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

## 🚀 Puesta en Marcha

### 1. Requisitos Previos
- Python 3.11+
- PostgreSQL 15+ (o levantar mediante Docker Compose en la raíz: `docker compose up -d`)

### 2. Entorno Virtual e Instalación
```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno (Linux/macOS)
source venv/bin/activate
# En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Variables de Entorno
Copia el archivo de ejemplo y edita las variables:
```bash
cp .env.example .env
```

### 4. Ejecutar el Servidor
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva disponible en:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
