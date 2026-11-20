"""
Adaptador de proveedores de IA (Vertex AI / Gemini y Ollama / Qwen 3.8) para el Asistente MC en vivo.

Sigue el patrón de `parcial_1/ia/app/providers/models.py`:
- Vertex AI (`google-genai`) con soporte para clave Express (`AQ.`) o proyecto/ubicación GCP.
- Ollama (`httpx`) con cabecera `ngrok-skip-browser-warning` y `think: False` para baja latencia.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

AiProviderName = Literal["vertex", "ollama"]

MC_SYSTEM_PROMPT_ES = """Eres el Maestro de Ceremonias (MC) oficial de la plataforma EXPERIENCIA.
Tu rol va más allá de un simple asistente: tú conduces el evento en tiempo real frente al público, dominas la temática de la experiencia y apoyas al anfitrión en todo momento.

Reglas de respuesta:
- Responde en español, de forma clara, carismática, práctica y accionable.
- Usa el contexto real de la experiencia (título, descripción, categoría, modalidad) y las métricas en vivo de la audiencia cuando estén disponibles.
- Si te piden una dinámica, discurso, explicación del tema o pregunta rompehielo, redacta contenido natural y listo para decirse al público.
- Nunca inventes métricas que no estén en el contexto."""

MC_SYSTEM_PROMPT_EN = """You are the official Live Master of Ceremonies (MC) for the EXPERIENCIA platform.
You actively host and guide the live event in front of the audience, know the event's subject matter deeply, and support the host at all times.

Response rules:
- Reply in English, clearly, charismatically, practically, and actionably.
- Use the real event context (title, description, category, modality) and live audience metrics when available.
- When asked for a dynamic, speech, topic insight, or icebreaker, provide natural content ready to be spoken to the audience.
- Never invent metrics not present in the context."""


class WelcomeSpeechOptionSchema(BaseModel):
    id: str = Field(..., description="Identificador corto: warm o energetic")
    style: str = Field(..., description="Estilo del discurso (ej. Cálido y cercano / Dinámico y energético)")
    title: str = Field(..., description="Título breve de la propuesta")
    speech_text: str = Field(
        ...,
        description="Discurso completo listo para ser leído en voz alta directamente al público, sin markdown ni acotaciones entre paréntesis.",
    )


class WelcomeSpeechesSchema(BaseModel):
    options: list[WelcomeSpeechOptionSchema] = Field(..., min_length=2, max_length=2)


class AutonomousSuggestionSchema(BaseModel):
    title: str = Field(..., description="Título corto de la intervención sugerida")
    reason: str = Field(..., description="Motivo breve basado en las métricas actuales del público")
    speech_text: str = Field(
        ...,
        description="Guion exacto y natural para que el Maestro de Ceremonias lo diga en voz alta directamente al público, sin markdown ni acotaciones.",
    )


class ChatReplySchema(BaseModel):
    reply: str = Field(
        ...,
        description="Respuesta breve para el anfitrión (en Markdown si ayuda). Si propones una dinámica o intervención, explica en 1-2 líneas la idea sin repetir el guion completo.",
    )
    speech_text: str | None = Field(
        default=None,
        description="Guion exacto y natural listo para que el Maestro de Ceremonias lo diga en voz alta directamente al público (SIN títulos, SIN 'Aquí tienes...', SIN 'Duración:', SIN viñetas ni acotaciones entre paréntesis). Déjalo en null únicamente si el mensaje es una consulta privada que no debe hablarse al público.",
    )


class DjTransitionSchema(BaseModel):
    recommended_playlist_id: Literal[
        "chill_jazz", "groove_funk", "melodic_house", "upbeat_party"
    ] = Field(..., description="Playlist objetivo según la energía de la audiencia")
    recommended_genre: str = Field(..., description="Género o estilo musical recomendado")
    recommended_bpm: str = Field(..., description="Tempo recomendado, ej. '112 BPM'")
    youtube_search_query: str = Field(
        ...,
        description="Consulta corta y precisa en inglés o español para buscar la música ideal en YouTube (ej. 'acoustic jazz lounge wine night mix' o 'melodic afro house dj set 122 bpm').",
    )
    reason: str = Field(..., description="Motivo breve basado en las métricas y temática del evento")
    dj_shoutout: str = Field(
        ...,
        description="Frase corta y carismática de DJ (1 a 2 oraciones naturales, SIN markdown ni acotaciones) para decir por micrófono al cambiar de ritmo.",
    )


WelcomeSpeechOptionSchema.model_rebuild()
WelcomeSpeechesSchema.model_rebuild()
AutonomousSuggestionSchema.model_rebuild()
ChatReplySchema.model_rebuild()
DjTransitionSchema.model_rebuild()


class McAiProviderService:
    """Gestiona la inferencia conversacional del Asistente MC con Vertex AI (Gemini) y Ollama (Qwen 3.8)."""

    def __init__(self, config: Settings | None = None) -> None:
        self.settings = config or default_settings
        self.http = httpx.Client(
            timeout=httpx.Timeout(
                timeout=float(self.settings.CHAT_TIMEOUT_SECONDS),
                connect=15.0,
            ),
            headers={"ngrok-skip-browser-warning": "true"},
        )
        self._google_client: genai.Client | None = None

    def _cloud(self) -> genai.Client:
        """Inicializa Google GenAI (Vertex AI regional o Express con clave `AQ.`)."""
        if self._google_client is None:
            options: dict[str, Any] = {
                "http_options": types.HttpOptions(
                    timeout=self.settings.CHAT_TIMEOUT_SECONDS * 1000
                )
            }
            api_key = (self.settings.GEMINI_API_KEY or "").strip()
            project_id = (self.settings.GCP_PROJECT_ID or "").strip()
            location = (self.settings.GCP_LOCATION or "us-central1").strip()

            if api_key:
                options["api_key"] = api_key
                if api_key.startswith("AQ."):
                    options["vertexai"] = True
                    if project_id:
                        options["project"] = project_id
                        options["location"] = location
            else:
                options["vertexai"] = True
                options["project"] = project_id
                options["location"] = location

            self._google_client = genai.Client(**options)
        return self._google_client

    def default_provider(self) -> AiProviderName:
        raw = (self.settings.CHAT_DEFAULT_PROVIDER or self.settings.AI_PROVIDER or "vertex").strip().lower()
        return "ollama" if raw == "ollama" else "vertex"

    def catalog(self) -> dict[str, Any]:
        """Informa los modelos configurados (Gemini 3.8 Flash y Qwen 3.8) y disponibilidad local."""
        ollama_available = False
        try:
            url = self.settings.OLLAMA_BASE_URL.rstrip("/") + "/api/tags"
            response = self.http.get(url, timeout=3.0)
            response.raise_for_status()
            models = response.json().get("models", [])
            target = self.settings.CHAT_OLLAMA_MODEL
            ollama_available = any(
                m.get("name") == target or m.get("model") == target for m in models
            )
        except Exception:
            ollama_available = False

        vertex_configured = bool(
            (self.settings.GEMINI_API_KEY or "").strip()
            or (self.settings.GCP_PROJECT_ID or "").strip()
        )

        return {
            "default_provider": self.default_provider(),
            "models": [
                {
                    "provider": "vertex",
                    "id": self.settings.GEMINI_MODEL,
                    "label": f"Gemini ({self.settings.GEMINI_MODEL})",
                    "available": vertex_configured,
                },
                {
                    "provider": "ollama",
                    "id": self.settings.CHAT_OLLAMA_MODEL,
                    "label": f"Qwen 3.8 ({self.settings.CHAT_OLLAMA_MODEL})",
                    "available": ollama_available,
                },
            ],
        }

    def _build_system_instruction(
        self,
        *,
        language: str,
        experience_context: dict[str, Any] | None,
        telemetry_context: dict[str, Any] | None,
    ) -> str:
        base = MC_SYSTEM_PROMPT_EN if language == "en" else MC_SYSTEM_PROMPT_ES
        parts = [base]

        if experience_context:
            exp_lines = ["\n--- CONTEXTO DE LA EXPERIENCIA ---"]
            if experience_context.get("title"):
                exp_lines.append(f"Título: {experience_context['title']}")
            if experience_context.get("category"):
                exp_lines.append(f"Categoría: {experience_context['category']}")
            if experience_context.get("modality"):
                exp_lines.append(f"Modalidad: {experience_context['modality']}")
            if experience_context.get("description"):
                desc = str(experience_context["description"]).strip()[:400]
                exp_lines.append(f"Descripción: {desc}")
            parts.append("\n".join(exp_lines))

        if telemetry_context:
            tel_lines = ["\n--- TELEMETRÍA EN VIVO DE LA AUDIENCIA ---"]
            for key, label in [
                ("signal_status", "Estado de señal"),
                ("traffic_light", "Semáforo de energía"),
                ("energy_score", "Energía (0-1)"),
                ("attention_score", "Atención (0-1)"),
                ("joy_score", "Alegría / Entusiasmo (0-1)"),
                ("inattention_score", "Desatención (0-1)"),
                ("detected_faces_count", "Rostros detectados"),
                ("trend", "Tendencia"),
                ("dominant_age_group", "Rango etario predominante"),
            ]:
                val = telemetry_context.get(key)
                if val is not None:
                    tel_lines.append(f"{label}: {val}")
            parts.append("\n".join(tel_lines))

        return "\n".join(parts)

    def chat(
        self,
        *,
        message: str,
        history: list[dict[str, str]],
        provider: AiProviderName | None = None,
        language: str = "es",
        experience_context: dict[str, Any] | None = None,
        telemetry_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Genera una respuesta conversacional con Vertex AI (Gemini) u Ollama (Qwen 3.8)."""
        chosen: AiProviderName = provider or self.default_provider()
        system_instruction = self._build_system_instruction(
            language=language,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
        )

        # Limitar historial a los últimos 12 mensajes para mantener respuestas ágiles
        recent_history = history[-12:]

        if chosen == "ollama":
            return self._chat_ollama(system_instruction, recent_history, message)
        return self._chat_vertex(system_instruction, recent_history, message)

    def _chat_ollama(
        self,
        system_instruction: str,
        history: list[dict[str, str]],
        message: str,
    ) -> dict[str, Any]:
        chat_instruction = (
            system_instruction
            + "\n\nResponde SIEMPRE en JSON con dos campos: "
            "`reply` (nota breve para el anfitrión) y `speech_text` (el discurso/guion exacto listo para leer en voz alta directo al público, sin títulos ni instrucciones, o null si no aplica hablarlo)."
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": chat_instruction}]
        for turn in history:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            content = str(turn.get("content", "")).strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        url = self.settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
        response = self.http.post(
            url,
            json={
                "model": self.settings.CHAT_OLLAMA_MODEL,
                "stream": False,
                "think": False,
                "format": ChatReplySchema.model_json_schema(),
                "options": {"temperature": 0.5},
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        raw_text = str(data.get("message", {}).get("content", "")).strip()
        if not raw_text:
            raise ValueError("Ollama devolvió una respuesta vacía.")

        reply_text = raw_text
        speech_text: str | None = None
        try:
            parsed = ChatReplySchema.model_validate_json(raw_text)
            reply_text = parsed.reply.strip()
            speech_text = parsed.speech_text.strip() if parsed.speech_text else None
        except Exception:
            pass

        return {
            "reply": reply_text,
            "speech_text": speech_text,
            "provider": "ollama",
            "model": self.settings.CHAT_OLLAMA_MODEL,
            "input_tokens": data.get("prompt_eval_count"),
            "output_tokens": data.get("eval_count"),
        }

    def _chat_vertex(
        self,
        system_instruction: str,
        history: list[dict[str, str]],
        message: str,
    ) -> dict[str, Any]:
        chat_instruction = (
            system_instruction
            + "\n\nResponde SIEMPRE en JSON con dos campos: "
            "`reply` (nota breve para el anfitrión) y `speech_text` (el discurso/guion exacto listo para leer en voz alta directo al público, sin títulos, sin 'Aquí tienes...', sin 'Duración:' ni acotaciones entre paréntesis; o null si es una pregunta privada que no va al público)."
        )
        contents: list[types.Content] = []
        for turn in history:
            role = "model" if turn.get("role") == "assistant" else "user"
            text = str(turn.get("content", "")).strip()
            if text:
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        response = self._cloud().models.generate_content(
            model=self.settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=chat_instruction,
                response_mime_type="application/json",
                response_json_schema=ChatReplySchema.model_json_schema(),
                temperature=0.5,
            ),
        )
        raw_text = (response.text or "").strip()
        if not raw_text:
            raise ValueError("Vertex AI devolvió una respuesta vacía.")

        reply_text = raw_text
        speech_text: str | None = None
        try:
            parsed = ChatReplySchema.model_validate_json(raw_text)
            reply_text = parsed.reply.strip()
            speech_text = parsed.speech_text.strip() if parsed.speech_text else None
        except Exception:
            pass

        usage = getattr(response, "usage_metadata", None)
        return {
            "reply": reply_text,
            "speech_text": speech_text,
            "provider": "vertex",
            "model": self.settings.GEMINI_MODEL,
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
        }

    def _generate_structured(
        self,
        *,
        provider: AiProviderName,
        system_instruction: str,
        user_prompt: str,
        schema_cls: type[BaseModel],
    ) -> tuple[BaseModel, dict[str, Any]]:
        """Genera JSON estructurado validado con Pydantic usando Vertex AI u Ollama."""
        if provider == "ollama":
            url = self.settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
            response = self.http.post(
                url,
                json={
                    "model": self.settings.CHAT_OLLAMA_MODEL,
                    "stream": False,
                    "think": False,
                    "format": schema_cls.model_json_schema(),
                    "options": {"temperature": 0.6},
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            raw = str(data.get("message", {}).get("content", "")).strip()
            return schema_cls.model_validate_json(raw), {
                "provider": "ollama",
                "model": self.settings.CHAT_OLLAMA_MODEL,
            }

        response = self._cloud().models.generate_content(
            model=self.settings.GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_json_schema=schema_cls.model_json_schema(),
                temperature=0.6,
            ),
        )
        raw = (response.text or "").strip()
        return schema_cls.model_validate_json(raw), {
            "provider": "vertex",
            "model": self.settings.GEMINI_MODEL,
        }

    def generate_welcome_speeches(
        self,
        *,
        provider: AiProviderName | None = None,
        language: str = "es",
        experience_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Genera exactamente 2 discursos de bienvenida listos para locución en vivo."""
        chosen: AiProviderName = provider or self.default_provider()
        system_instruction = self._build_system_instruction(
            language=language,
            experience_context=experience_context,
            telemetry_context=None,
        )
        if language == "en":
            prompt = (
                "Generate EXACTLY 2 distinct live welcome speeches to open this event as the Master of Ceremonies.\n"
                "- Option 1 (id='warm'): Warm, welcoming, and close tone.\n"
                "- Option 2 (id='energetic'): Energetic, fun, and engaging tone.\n"
                "Each speech_text must be 3 to 5 natural spoken sentences (about 25-40 seconds when read aloud), "
                "addressed directly to the audience, mentioning the event's theme naturally, with NO markdown, NO bullet points, and NO stage directions."
            )
        else:
            prompt = (
                "Genera EXACTAMENTE 2 propuestas distintas de discurso de bienvenida para abrir este evento como Maestro de Ceremonias.\n"
                "- Opción 1 (id='warm'): estilo Cálido y cercano.\n"
                "- Opción 2 (id='energetic'): estilo Dinámico y energético.\n"
                "Cada speech_text debe tener entre 3 y 5 oraciones naturales habladas (unos 25 a 40 segundos en voz alta), "
                "dirigidas directamente al público, presentando la temática del evento con soltura, SIN markdown, SIN viñetas y SIN acotaciones entre paréntesis."
            )

        parsed, meta = self._generate_structured(
            provider=chosen,
            system_instruction=system_instruction,
            user_prompt=prompt,
            schema_cls=WelcomeSpeechesSchema,
        )
        data = parsed.model_dump()
        return {
            "options": data["options"],
            "provider": meta["provider"],
            "model": meta["model"],
        }

    def generate_autonomous_suggestion(
        self,
        *,
        provider: AiProviderName | None = None,
        language: str = "es",
        experience_context: dict[str, Any] | None = None,
        telemetry_context: dict[str, Any] | None = None,
        recent_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Genera una intervención autónoma cada minuto basada en las métricas actuales y el tema."""
        chosen: AiProviderName = provider or self.default_provider()
        system_instruction = self._build_system_instruction(
            language=language,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
        )
        history_snippet = ""
        if recent_history:
            lines = [
                f"- {m.get('role')}: {str(m.get('content', ''))[:160]}"
                for m in recent_history[-6:]
            ]
            history_snippet = "\nIntervenciones recientes (NO repetir lo mismo):\n" + "\n".join(lines)

        if language == "en":
            prompt = (
                "You are monitoring the audience every minute as the live Master of Ceremonies. "
                "Based on the live metrics and the event topic, propose ONE concrete spoken intervention you can deliver out loud right now "
                "(e.g., an engaging question, an interesting fact about the event's topic, a quick energizer, or encouragement if energy is already high).\n"
                "Keep speech_text to 2-4 natural spoken sentences ready for TTS (NO markdown, NO stage directions)."
                f"{history_snippet}"
            )
        else:
            prompt = (
                "Estás monitoreando a la audiencia cada minuto como Maestro de Ceremonias en vivo. "
                "Según las métricas actuales y la temática del evento, propón UNA intervención concreta para decir en voz alta ahora mismo "
                "(por ejemplo: una pregunta participativa, un dato interesante o consejo sobre la temática del evento, una micro-dinámica si bajó la energía, o un comentario motivador si la energía está alta).\n"
                "Redacta speech_text en 2 a 4 oraciones naturales listas para hablar por micrófono (SIN markdown ni acotaciones entre paréntesis)."
                f"{history_snippet}"
            )

        parsed, meta = self._generate_structured(
            provider=chosen,
            system_instruction=system_instruction,
            user_prompt=prompt,
            schema_cls=AutonomousSuggestionSchema,
        )
        data = parsed.model_dump()
        return {
            "title": data["title"],
            "reason": data["reason"],
            "speech_text": data["speech_text"],
            "provider": meta["provider"],
            "model": meta["model"],
        }

    def generate_dj_transition(
        self,
        *,
        provider: AiProviderName | None = None,
        language: str = "es",
        current_playlist_id: str | None = None,
        experience_context: dict[str, Any] | None = None,
        telemetry_context: dict[str, Any] | None = None,
        recent_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Recomienda cambio de playlist/BPM y genera una frase de DJ lista para locución."""
        chosen: AiProviderName = provider or self.default_provider()
        system_instruction = self._build_system_instruction(
            language=language,
            experience_context=experience_context,
            telemetry_context=telemetry_context,
        )
        playlists_desc = (
            "Playlists disponibles:\n"
            "- chill_jazz: Jazz Acústico & Lounge (92 BPM) — ambiente relajado, creativo o bienvenida.\n"
            "- groove_funk: Groove & Nu-Disco (112 BPM) — energía media, conversación y fluidez.\n"
            "- melodic_house: House Melódico & Afro (122 BPM) — energía alta, ritmo envolvente.\n"
            "- upbeat_party: Upbeat & Latin Pop (128 BPM) — reactivación fuerte cuando baja la atención."
        )
        current_info = (
            f"\nPlaylist actual sonando: {current_playlist_id}."
            if current_playlist_id
            else ""
        )
        avoid_snippet = ""
        if recent_history:
            prev_lines = [
                f"- {str(m.get('content', ''))[:140]}"
                for m in recent_history[-6:]
                if m.get("role") == "assistant"
            ]
            if prev_lines:
                avoid_snippet = (
                    "\nFrases/transiciones ya usadas (DEBES proponer una búsqueda en YouTube y una frase de DJ DIFERENTES, frescas y originales):\n"
                    + "\n".join(prev_lines)
                )
        if language == "en":
            prompt = (
                "You are the Autonomous Live DJ for this event. Analyze the live audience energy/attention, "
                "event theme, and current playlist, then choose the best playlist from the 4 available IDs, "
                "provide a fresh youtube_search_query, and write a new charismatic DJ mic transition "
                "(1-2 natural sentences, NO markdown, NO stage directions).\n"
                f"{playlists_desc}{current_info}{avoid_snippet}"
            )
        else:
            prompt = (
                "Eres el DJ Autónomo en vivo de este evento. Analiza la energía/atención actual del público, "
                "la temática de la experiencia y la playlist actual, elige la mejor playlist entre las 4 opciones, "
                "propón una búsqueda nueva en `youtube_search_query` y escribe una frase corta, creativa y diferente de DJ "
                "para decir al micrófono durante la transición (1 a 2 oraciones naturales, SIN markdown ni acotaciones).\n"
                f"{playlists_desc}{current_info}{avoid_snippet}"
            )

        parsed, meta = self._generate_structured(
            provider=chosen,
            system_instruction=system_instruction,
            user_prompt=prompt,
            schema_cls=DjTransitionSchema,
        )
        data = parsed.model_dump()
        return {
            "recommended_playlist_id": data["recommended_playlist_id"],
            "recommended_genre": data["recommended_genre"],
            "recommended_bpm": data["recommended_bpm"],
            "youtube_search_query": data["youtube_search_query"],
            "reason": data["reason"],
            "dj_shoutout": data["dj_shoutout"],
            "provider": meta["provider"],
            "model": meta["model"],
        }

    def close(self) -> None:
        self.http.close()
        if self._google_client is not None:
            self._google_client.close()


_mc_ai_provider_service: McAiProviderService | None = None


def get_mc_ai_provider_service() -> McAiProviderService:
    global _mc_ai_provider_service
    if _mc_ai_provider_service is None:
        _mc_ai_provider_service = McAiProviderService()
    return _mc_ai_provider_service
