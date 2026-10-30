# Matching, avisos y demanda — sprint 2

[Índice](README.md) · [Matching](../app/matching/service/matching_service.py) · [Demanda](../app/matching/service/demand_prediction_service.py) · [Avisos](../app/notifications/service.py)

CU-06 cubre HU-08/HU-09; CU-07 cubre HU-10/HU-11.

## Matching

POST /api/matching/apply recibe experience_id, available_from/available_to opcionales y preferred_zone. El perfil aporta intereses; la categoría del evento se añade como interés explícito. Se rechazan eventos no disponibles, disponibilidades que no cubren toda su duración y zonas incompatibles con la sede.

El servicio bloquea la experiencia antes de decidir grupo/membresía. Compara etiquetas normalizadas por Jaccard, selecciona el grupo con mayor afinidad media si alcanza 0,15, o crea otro. La comparación admite tildes/mayúsculas/espacios y no se presenta como un modelo entrenado. Unicidad usuario/grupo y la serialización por experiencia evitan postulaciones duplicadas.

GET /api/matching/group/{experience_id} consulta sin escribir ni inscribir; devuelve el grupo propio o uno disponible. Sin grupo devuelve 404. DELETE /api/matching/group/{experience_id}/membership retira interés sin tocar reservas. La respuesta contiene is_member, affinity_score, current_members, paid_slots y experience_confirmed; no publica identidades de integrantes.

El plazo del grupo termina 30 minutos antes del evento. GET calcula EXPIRED al vencer, incluso antes de ejecutar scripts/expire_matching_groups.py. El mantenimiento persiste el vencimiento y un aviso recuperable. REACHED expresa interés suficiente: invita a reservar, sin emitir entradas ni confirmar quórum económico.

## Avisos de quórum

notifications se inserta dentro de la transacción del caso de uso. Claves únicas por destinatario/tipo/generación absorben reintentos. Al cruzar el mínimo pagado se notifica al anfitrión y compradores; compradores posteriores de un evento confirmado reciben su aviso. Una devolución que vuelve a dejar el evento bajo el mínimo genera QUORUM_LOST; una nueva confirmación usa otra generación.

MATCHING_READY convoca a reservar. EVENT_CANCELLED invalida la participación y avisa del trámite de devolución. No confundir estos estados con QUORUM_CONFIRMED.

GET /api/notifications?limit=50&offset=0 lista solo avisos propios. PATCH /api/notifications/{id}/read marca uno propio de manera idempotente; ajenos/inexistentes devuelven 404. Web y móvil recuperan la bandeja al abrirla y consultan cada 30 segundos. No hay push con la app cerrada ni un canal WebSocket de quórum.

## Demanda basada en evidencia

El catálogo registra resultados efectivos de la primera página cuando hay intención de búsqueda. X-Search-Session identifica una sesión efímera; se guarda solo una huella de filtros/sesión/ventana de cinco minutos. Paginar o reintentar no suma otra consulta. El POST histórico /api/demand/log-search recalcula resultados; ignora found_results del cliente.

SearchLog guarda filtros (presupuesto/fecha incluidos), zona/categoría/texto normalizados y presencia de oferta. Los agregados usan búsquedas sin oferta de los últimos 30 días y excluyen registros antiguos sin evidencia deduplicada.

GET /api/demand/insights y /api/demand/suggestions admiten zone opcional. Requieren HOST, VENUE o ADMIN. El tablero es exclusivo web. Devuelve hasta 100 segmentos por volumen; para precio/franja usa hasta 500 filtros recientes por segmento. Las consultas no publican búsquedas individuales ni cuentas.

Las recomendaciones explican búsquedas observadas, presupuesto mediano y franja solicitada en Bolivia cuando existen datos. Sin esos filtros, precio/franja son null; confidence_score permanece null. No se afirma rentabilidad, número de personas únicas ni precisión predictiva. Se conserva UnmetDemand para compatibilidad; el tablero consulta SearchLog, evitando un agregado obsoleto.

La validación de un modelo aprendido requiere datos reales etiquetados y evaluación adicional. SaaS conserva alcance condicionado entre sprints 2/4; visión, live y MC/DJ pertenecen a incrementos posteriores.
