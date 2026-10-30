# Experiencias y catálogo

[Índice](README.md) · [Servicio](../app/experience/service/experience_service.py) · [DTO](../app/experience/dto/experience_dto.py) · [Mapper](../app/experience/mapper/experience_mapper.py)

CU-03 publica experiencias; CU-04 explora el catálogo. Las etiquetas públicas del controlador usan CU-03/CU-04.

`POST /api/experiences` permite HOST/VENUE. IN_PERSON e HYBRID requieren `venue_id` propio existente; `venue_name` no lo sustituye. Se validan categoría, fecha futura, mínimos/máximos, capacidad del local y cruces de horario. VIRTUAL elimina la sede asociada.

`PUT /api/experiences/{id}` exige propiedad, fecha futura y ausencia de asistentes, retenciones vigentes y postulaciones. `DELETE /api/experiences/{id}` exige además ausencia de historial de reservas. Ver [reglas de gestión](08-ROLES-Y-ADMINISTRACION.md). Cancelación usa `PATCH /api/experiences/{id}/cancel`. `GET /api/experiences/me/hosted` lista las publicaciones del sujeto.

## Catálogo

`GET /api/experiences/catalog` devuelve `total`, `page`, `page_size`, `total_pages`, `experiences`. `ExperienceRepository` filtra OPEN/CONFIRMED y admite:

- `category_id`, `modality`, `search`, `zone`, `max_price`.
- `date_from`, `date_to` con rango válido.
- `latitude`, `longitude`, `radius_km` enviados juntos; distancia Haversine ejecutada por PostgreSQL.
- `only_available`, `page`, `page_size`.

`ExperienceMapper` añade `venue_zone`, `venue_address`, nombres, disponibilidad y distancia. Al cambiar campos, actualizar web y Flutter; no adaptar datos solo en una pantalla.

## Contratos integrados y límites

La web selecciona venue_id y usa venue_zone/venue_address. Las fechas del formulario se convierten de hora de Bolivia a UTC. Web y móvil consultan filtros y páginas del servidor.

El mapper y /commission-quote comparten quote_price(), que calcula con Decimal usando los escalones existentes de la web. El formulario consulta esa API. Las proyecciones se diferencian del resumen contable realizado de /bookings/host-income; la compra real Stripe requiere configuración y demostración externa.

available_slots descuenta retenciones vigentes; reserved_slots permanece como cupos confirmados. Editar precio/aforo bloquea la experiencia y considera sus retenciones. Cancelar invalida pendientes y encola devoluciones de pagos verificados; cobros históricos sin conciliación impiden cancelar. El catálogo también registra búsquedas efectivas para demanda. PostgreSQL real todavía no se ha podido verificar.
