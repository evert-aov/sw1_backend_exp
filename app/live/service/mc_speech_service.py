"""
Servicio de síntesis de voz (Edge TTS) para el Maestro de Ceremonias en vivo.

Basado en `parcial_1/ia/app/providers/edge_speech.py` y `parcial_1/ia/app/speech.py`:
- Usa Microsoft Edge TTS (`es-BO-MarceloNeural` en español, `en-US-AndrewNeural` en inglés).
- Limpia Markdown antes de sintetizar para que la locución suene natural.
- Reintenta una vez ante fallos transitorios de red.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import aclosing
from typing import Literal

import aiohttp
import edge_tts

logger = logging.getLogger(__name__)

SpeechVoice = Literal["marcelo", "sofia", "andrew"]
VOICE_IDS: dict[str, str] = {
    "marcelo": "es-BO-MarceloNeural",
    "sofia": "es-BO-SofiaNeural",
    "andrew": "en-US-AndrewNeural",
}
MAX_AUDIO_BYTES = 5_000_000
MAX_SPEECH_CHARS = 6000


def clean_text_for_speech(raw_text: str) -> str:
    """Elimina sintaxis Markdown y HTML para una lectura natural por voz."""
    text = re.sub(r"```[\s\S]*?(?:```|$)", "", raw_text or "")
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|>|[-*+•])\s+", "", text)
    text = re.sub(r"(?m)^-{3,}$", "", text)
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("El texto para sintetizar voz está vacío.")
    return text[:MAX_SPEECH_CHARS]


class McEdgeSpeechService:
    """Sintetiza locuciones del Maestro de Ceremonias en formato audio/mpeg con Edge TTS."""

    async def synthesize_mpeg(
        self,
        text: str,
        *,
        voice: str = "marcelo",
        language: str = "es",
    ) -> bytes:
        spoken = clean_text_for_speech(text)
        voice_id = VOICE_IDS.get(voice) or (
            VOICE_IDS["andrew"] if language == "en" else VOICE_IDS["marcelo"]
        )

        for attempt in range(2):
            try:
                return await self._synthesize_once(spoken, voice_id)
            except (
                aiohttp.ClientError,
                TimeoutError,
                edge_tts.exceptions.NoAudioReceived,
                edge_tts.exceptions.WebSocketError,
            ) as exc:
                if attempt or (
                    isinstance(exc, aiohttp.ClientResponseError)
                    and exc.status not in {408, 429, 500, 502, 503, 504}
                ):
                    raise
                logger.warning("Edge TTS retry (%s)", type(exc).__name__)
                await asyncio.sleep(0.5)
        raise RuntimeError("No se pudo sintetizar audio con Edge TTS.")

    async def _synthesize_once(self, text: str, voice_id: str) -> bytes:
        audio = bytearray()
        communication = edge_tts.Communicate(
            text,
            voice_id,
            connect_timeout=6,
            receive_timeout=15,
        )
        async with aclosing(communication.stream()) as stream:
            async for chunk in stream:
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                    if len(audio) > MAX_AUDIO_BYTES:
                        raise ValueError("El audio supera el tamaño máximo permitido.")
        if not audio:
            raise edge_tts.exceptions.NoAudioReceived("Edge TTS no devolvió audio.")
        return bytes(audio)


_speech_service: McEdgeSpeechService | None = None


def get_mc_speech_service() -> McEdgeSpeechService:
    global _speech_service
    if _speech_service is None:
        _speech_service = McEdgeSpeechService()
    return _speech_service
