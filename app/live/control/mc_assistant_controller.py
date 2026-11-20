from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.entity.user import User
from app.auth.repository.user_repository import UserRepository
from app.core.database import SessionLocal
from app.core.security import get_current_active_user, get_current_token
from app.live.dto.mc_assistant_dto import (
    DjTransitionRequestDTO,
    DjTransitionResponseDTO,
    DjYoutubeSearchResponseDTO,
    McAiCatalogDTO,
    McAiChatHistoryDTO,
    McAiChatRequestDTO,
    McAiChatResponseDTO,
    McAlertDTO,
    McAutonomousSuggestionRequestDTO,
    McAutonomousSuggestionResponseDTO,
    McDynamicDTO,
    McSpeechRequestDTO,
    McWelcomeSpeechRequestDTO,
    McWelcomeSpeechesResponseDTO,
    PushDeviceRegisterDTO,
    PushDeviceRegisteredDTO,
    PushDeviceRemoveDTO,
)
from app.live.service.live_monitor_pairing import decode_monitor_token, monitor_token_expiry
from app.live.service.live_telemetry_access import (
    CONSOLE_ROLES,
    SessionActor,
    TelemetryAccessError,
    authorize_session_actor,
)
from app.live.service.live_telemetry_service import get_live_telemetry_hub
from app.live.service.mc_ai_providers import McAiProviderService, get_mc_ai_provider_service
from app.live.service.mc_assistant_service import McAssistantService, get_mc_assistant_service
from app.live.service.mc_chat_memory import (
    clear_event_messages,
    list_event_messages,
    resolve_event_context,
    save_chat_exchange,
)
from app.live.service.mc_speech_service import McEdgeSpeechService, get_mc_speech_service
from app.live.service.youtube_search_service import (
    YoutubeMusicSearchService,
    get_youtube_music_search_service,
)

mc_assistant_router = APIRouter(
    prefix="/mc",
    tags=["Live MC Assistant (CU-11 / HU-18, HU-19)"],
)


def _authorize(session_id: str, token: str) -> SessionActor:
    """
    Autoriza al anfitrión (JWT) o al monitor vinculado (token de monitor) sobre la sesión.

    Args:
        session_id (str): ID de la sesión en vivo.
        token (str): Token Bearer recibido.

    Returns:
        SessionActor: Sesión autorizada y tipo de actor.

    Raises:
        HTTPException (401/403/404/422): Según el motivo del rechazo.
    """
    with SessionLocal() as db:
        try:
            return authorize_session_actor(db, session_id, token)
        except TelemetryAccessError as exc:
            raise exc.to_http_exception() from exc


async def _authorize_alert(alert_id: str, token: str, service: McAssistantService) -> None:
    """
    Verifica que la alerta exista y que el actor administre su sesión.

    Args:
        alert_id (str): UUID de la alerta.
        token (str): Token Bearer recibido.
        service (McAssistantService): Asistente MC del proceso.

    Raises:
        HTTPException (404): Si la alerta no existe o el ID no es válido.
        HTTPException (401/403): Si el actor no puede administrar la sesión.
    """
    try:
        session_id = await asyncio.to_thread(service.store.get_alert_session, alert_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada"
        ) from exc
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")
    await asyncio.to_thread(_authorize, session_id, token)


@mc_assistant_router.get(
    "/dynamics",
    response_model=list[McDynamicDTO],
    summary="Consultar el catálogo de dinámicas del Asistente MC (HU-19)",
    description="Devuelve las dinámicas activas con textos en español e inglés. Requiere rol de anfitrión.",
)
async def list_mc_dynamics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> list[McDynamicDTO]:
    """
    Lista el catálogo de dinámicas del Asistente MC (HU-19).

    Args:
        current_user (User): Usuario autenticado y activo.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        list[McDynamicDTO]: Dinámicas activas.

    Raises:
        HTTPException (403): Si el usuario no tiene rol de anfitrión.
    """
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    return await asyncio.to_thread(service.store.list_dynamics)


@mc_assistant_router.get(
    "/sessions/{session_id}/alerts",
    response_model=list[McAlertDTO],
    summary="Consultar el historial de alertas del Asistente MC de una sesión (HU-18)",
    description="Acepta el JWT del anfitrión propietario, de un administrador o el token del monitor vinculado.",
)
async def list_mc_alerts(
    session_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> list[McAlertDTO]:
    """
    Lista las alertas de la sesión, de la más reciente a la más antigua (HU-18).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        list[McAlertDTO]: Historial de alertas.
    """
    actor = await asyncio.to_thread(_authorize, session_id, token)
    return await asyncio.to_thread(service.store.list_alerts, actor.session_id)


@mc_assistant_router.post(
    "/sessions/{session_id}/request",
    response_model=McAlertDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir una dinámica al Asistente MC sin esperar la alerta (HU-19)",
    description="Crea una alerta manual con una dinámica sugerida; si ya hay una activa, la devuelve.",
)
async def request_mc_dynamic(
    session_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Crea una alerta manual con una dinámica sugerida (HU-19).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta activa con su dinámica.
    """
    actor = await asyncio.to_thread(_authorize, session_id, token)
    return await service.request_dynamic(actor.session_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/apply",
    response_model=McAlertDTO,
    summary="Aplicar la dinámica sugerida (HU-19)",
    description="Marca la dinámica como aplicada. Si es una pausa, fija `break_ends_at` y suspende alertas hasta el regreso.",
)
async def apply_mc_alert(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Aplica la dinámica de una alerta activa (HU-19).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta aplicada.

    Raises:
        HTTPException (409): Si la alerta ya fue atendida.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.apply(alert_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/dismiss",
    response_model=McAlertDTO,
    summary="Descartar la dinámica sugerida (HU-18)",
)
async def dismiss_mc_alert(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Descarta una alerta activa sin aplicar la dinámica (HU-18).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta descartada.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.dismiss(alert_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/next",
    response_model=McAlertDTO,
    summary="Proponer otra dinámica para la alerta activa (HU-19)",
)
async def next_mc_dynamic(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Cambia la dinámica sugerida de una alerta activa (HU-19).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta con otra dinámica.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.next_dynamic(alert_id)


@mc_assistant_router.post(
    "/monitor/push-device",
    response_model=PushDeviceRegisteredDTO,
    summary="Registrar el celular vinculado para recibir alertas push (HU-18)",
    description=(
        "Solo acepta el token de monitor obtenido al vincular el dispositivo. El registro dura lo mismo "
        "que el token de monitor y mantiene activa la evaluación de la sesión aunque la app esté cerrada."
    ),
)
async def register_monitor_push_device(
    dto: PushDeviceRegisterDTO,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> PushDeviceRegisteredDTO:
    """
    Registra el token de Firebase del monitor vinculado (HU-18).

    Args:
        dto (PushDeviceRegisterDTO): Token de Firebase, plataforma e idioma.
        token (str): Token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        PushDeviceRegisteredDTO: Resultado del registro.

    Raises:
        HTTPException (401): Si el token no es un token de monitor válido.
    """
    claims = decode_monitor_token(token)
    expires_at = monitor_token_expiry(token)
    if claims is None or expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Requiere el token del monitor vinculado",
        )
    actor = await asyncio.to_thread(_authorize, claims.session_id, token)
    return await service.register_push_device(
        actor.session_id, dto.fcm_token, dto.platform, dto.language, expires_at
    )


@mc_assistant_router.post(
    "/monitor/push-device/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dejar de enviar alertas push al celular vinculado (HU-18)",
    description="Solo acepta el token de monitor; elimina el dispositivo únicamente de su propia sesión.",
)
async def remove_monitor_push_device(
    dto: PushDeviceRemoveDTO,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> None:
    """
    Da de baja el token de Firebase del monitor al desvincularlo (HU-18).

    Args:
        dto (PushDeviceRemoveDTO): Token de Firebase a eliminar.
        token (str): Token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Raises:
        HTTPException (401): Si el token no es un token de monitor válido.
    """
    claims = decode_monitor_token(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Requiere el token del monitor vinculado",
        )
    actor = await asyncio.to_thread(_authorize, claims.session_id, token)
    await asyncio.to_thread(
        service.store.remove_session_push_device, actor.session_id, dto.fcm_token
    )


@mc_assistant_router.get(
    "/ai/models",
    response_model=McAiCatalogDTO,
    summary="Consultar los modelos de IA disponibles para el chat del Asistente MC",
)
async def get_mc_ai_models(
    current_user: Annotated[User, Depends(get_current_active_user)],
    ai_service: Annotated[McAiProviderService, Depends(get_mc_ai_provider_service)],
) -> McAiCatalogDTO:
    """Devuelve la configuración y disponibilidad de Gemini 3.8 Flash (Vertex) y Qwen 3.8 (Ollama)."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    catalog = await asyncio.to_thread(ai_service.catalog)
    return McAiCatalogDTO.model_validate(catalog)


@mc_assistant_router.get(
    "/sessions/{session_id}/chat",
    response_model=McAiChatHistoryDTO,
    summary="Recuperar la memoria de conversación del Asistente MC para el evento",
)
async def get_mc_chat_history(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> McAiChatHistoryDTO:
    """Devuelve el historial persistido de la IA para este evento y el nombre del evento."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    event_key, experience_context = await asyncio.to_thread(resolve_event_context, session_id)
    messages = await asyncio.to_thread(list_event_messages, event_key, 50)
    return McAiChatHistoryDTO.model_validate(
        {
            "event_key": event_key,
            "event_title": experience_context.get("title") if experience_context else None,
            "event_status": experience_context.get("status") if experience_context else None,
            "live_session_id": experience_context.get("live_session_id") if experience_context else None,
            "messages": messages,
        }
    )


@mc_assistant_router.delete(
    "/sessions/{session_id}/chat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Limpiar la memoria de conversación del Asistente MC para el evento",
)
async def clear_mc_chat_history(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Borra el historial persistido de la IA para este evento."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    event_key, _ = await asyncio.to_thread(resolve_event_context, session_id)
    await asyncio.to_thread(clear_event_messages, event_key)


@mc_assistant_router.post(
    "/sessions/{session_id}/chat",
    response_model=McAiChatResponseDTO,
    summary="Conversar en vivo con el Asistente MC impulsado por Gemini 3.8 Flash o Qwen 3.8",
)
async def chat_with_mc_assistant(
    session_id: str,
    dto: McAiChatRequestDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    ai_service: Annotated[McAiProviderService, Depends(get_mc_ai_provider_service)],
) -> McAiChatResponseDTO:
    """Genera una respuesta contextual del Asistente MC con memoria persistente por evento."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )

    event_key, experience_context = await asyncio.to_thread(resolve_event_context, session_id)
    stored_messages = await asyncio.to_thread(list_event_messages, event_key, 16)

    telemetry_context: dict[str, object] | None = (
        dto.telemetry.model_dump(exclude_none=True) if dto.telemetry is not None else None
    )
    if telemetry_context is None:
        try:
            hub = get_live_telemetry_hub()
            snapshot = await hub.get_snapshot(session_id)
            if snapshot.energy_score is not None or snapshot.attention_score is not None:
                telemetry_context = {
                    "signal_status": snapshot.signal_status.value,
                    "traffic_light": snapshot.traffic_light.value if snapshot.traffic_light else None,
                    "energy_score": snapshot.energy_score,
                    "attention_score": snapshot.attention_score,
                    "joy_score": snapshot.joy_score,
                    "detected_faces_count": snapshot.detected_faces_count,
                    "trend": snapshot.trend.value,
                    "dominant_age_group": (
                        snapshot.dominant_age_group.value if snapshot.dominant_age_group else None
                    ),
                }
        except Exception:
            telemetry_context = None

    if stored_messages:
        history = [{"role": m["role"], "content": m["content"]} for m in stored_messages]
    else:
        history = [{"role": turn.role, "content": turn.content} for turn in dto.history]

    try:
        result = await asyncio.to_thread(
            ai_service.chat,
            message=dto.message,
            history=history,
            provider=dto.provider,
            language=dto.language,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo obtener respuesta del modelo de IA ({dto.provider or ai_service.default_provider()}): {exc}",
        ) from exc

    await asyncio.to_thread(
        save_chat_exchange,
        event_key=event_key,
        user_message=dto.message,
        assistant_reply=result["reply"],
        provider=result["provider"],
        model=result["model"],
    )

    return McAiChatResponseDTO.model_validate(result)


@mc_assistant_router.post(
    "/sessions/{session_id}/welcome-speeches",
    response_model=McWelcomeSpeechesResponseDTO,
    summary="Generar 2 propuestas de discurso de bienvenida del Maestro de Ceremonias",
)
async def generate_mc_welcome_speeches(
    session_id: str,
    dto: McWelcomeSpeechRequestDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    ai_service: Annotated[McAiProviderService, Depends(get_mc_ai_provider_service)],
) -> McWelcomeSpeechesResponseDTO:
    """Genera 2 discursos de bienvenida basados en la temática del evento para que el anfitrión elija uno."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )

    _, experience_context = await asyncio.to_thread(resolve_event_context, session_id)
    try:
        result = await asyncio.to_thread(
            ai_service.generate_welcome_speeches,
            provider=dto.provider,
            language=dto.language,
            experience_context=experience_context,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudieron generar los discursos de bienvenida: {exc}",
        ) from exc
    return McWelcomeSpeechesResponseDTO.model_validate(result)


@mc_assistant_router.post(
    "/sessions/{session_id}/autonomous-suggestion",
    response_model=McAutonomousSuggestionResponseDTO,
    summary="Generar una sugerencia autónoma del Maestro de Ceremonias según métricas en vivo",
)
async def generate_mc_autonomous_suggestion(
    session_id: str,
    dto: McAutonomousSuggestionRequestDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    ai_service: Annotated[McAiProviderService, Depends(get_mc_ai_provider_service)],
) -> McAutonomousSuggestionResponseDTO:
    """Evalúa las métricas actuales y propone una intervención lista para hablar si el anfitrión la aprueba."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )

    event_key, experience_context = await asyncio.to_thread(resolve_event_context, session_id)
    stored_messages = await asyncio.to_thread(list_event_messages, event_key, 8)
    telemetry_context = (
        dto.telemetry.model_dump(exclude_none=True) if dto.telemetry is not None else None
    )

    try:
        result = await asyncio.to_thread(
            ai_service.generate_autonomous_suggestion,
            provider=dto.provider,
            language=dto.language,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
            recent_history=stored_messages,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo generar la sugerencia autónoma: {exc}",
        ) from exc
    return McAutonomousSuggestionResponseDTO.model_validate(result)


@mc_assistant_router.post(
    "/speech",
    summary="Sintetizar en audio (Edge TTS) una locución del Maestro de Ceremonias",
)
async def synthesize_mc_speech(
    dto: McSpeechRequestDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    speech_service: Annotated[McEdgeSpeechService, Depends(get_mc_speech_service)],
) -> Response:
    """Convierte el discurso o sugerencia aprobada en audio MPEG usando Edge TTS."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )

    try:
        audio_bytes = await speech_service.synthesize_mpeg(
            dto.text, voice=dto.voice, language=dto.language
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo sintetizar la voz del Maestro de Ceremonias: {exc}",
        ) from exc

    if dto.record_in_session_id:
        try:
            event_key, _ = await asyncio.to_thread(resolve_event_context, dto.record_in_session_id)
            await asyncio.to_thread(
                save_chat_exchange,
                event_key=event_key,
                user_message="[Locución aprobada por el anfitrión]",
                assistant_reply=dto.text,
                provider=dto.provider or "vertex",
                model=dto.model or "edge-tts",
            )
        except Exception:
            pass

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@mc_assistant_router.post(
    "/sessions/{session_id}/dj-transition",
    response_model=DjTransitionResponseDTO,
    summary="Generar transición musical y locución del DJ Autónomo según métricas en vivo",
)
async def generate_dj_transition(
    session_id: str,
    dto: DjTransitionRequestDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    ai_service: Annotated[McAiProviderService, Depends(get_mc_ai_provider_service)],
) -> DjTransitionResponseDTO:
    """Recomienda playlist/BPM y frase de DJ con IA, persistiendo en `live_suggestions` si hay sesión."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )

    event_key, experience_context = await asyncio.to_thread(resolve_event_context, session_id)
    stored_messages = await asyncio.to_thread(list_event_messages, event_key, 8)
    telemetry_context = (
        dto.telemetry.model_dump(exclude_none=True) if dto.telemetry is not None else None
    )

    try:
        result = await asyncio.to_thread(
            ai_service.generate_dj_transition,
            provider=dto.provider,
            language=dto.language,
            current_playlist_id=dto.current_playlist_id,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
            recent_history=stored_messages,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo generar la transición del DJ Autónomo: {exc}",
        ) from exc

    youtube_tracks: list[dict[str, object]] = []
    if result.get("youtube_search_query"):
        try:
            yt_service = get_youtube_music_search_service()
            youtube_tracks = await asyncio.to_thread(
                yt_service.search, str(result["youtube_search_query"]), max_results=3
            )
        except Exception:
            youtube_tracks = []
    result["youtube_tracks"] = youtube_tracks

    live_session_id = experience_context.get("live_session_id") if experience_context else None
    if live_session_id:
        try:
            from app.live.entity.live_suggestion import LiveSuggestion, SuggestionTypeEnum

            with SessionLocal() as db:
                db.add(
                    LiveSuggestion(
                        live_session_id=str(live_session_id),
                        suggestion_type=SuggestionTypeEnum.DJ_MUSIC_CHANGE,
                        suggestion_text=f"{result['reason']} — \"{result['dj_shoutout']}\"",
                        recommended_bpm=result["recommended_bpm"],
                        recommended_genre=result["recommended_genre"],
                        applied_by_host=False,
                    )
                )
                db.commit()
        except Exception:
            pass

    return DjTransitionResponseDTO.model_validate(result)


@mc_assistant_router.get(
    "/dj/youtube/search",
    response_model=DjYoutubeSearchResponseDTO,
    summary="Buscar música embebible en YouTube Data API v3 para el DJ Virtual",
)
async def search_dj_youtube_music(
    q: Annotated[str, Query(min_length=2, max_length=120)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    yt_service: Annotated[YoutubeMusicSearchService, Depends(get_youtube_music_search_service)],
    max_results: Annotated[int, Query(ge=1, le=8)] = 5,
) -> DjYoutubeSearchResponseDTO:
    """Busca videos musicales embebibles en YouTube usando la YOUTUBE_API_KEY configurada."""
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    try:
        tracks = await asyncio.to_thread(yt_service.search, q, max_results=max_results)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "YouTube Data API v3 rechazó la búsqueda. Verifica que 'YouTube Data API v3' esté "
                f"habilitada y permitida en tu API key de Google Cloud: {exc}"
            ),
        ) from exc
    return DjYoutubeSearchResponseDTO.model_validate({"query": q, "tracks": tracks})
