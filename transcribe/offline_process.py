import json
import os
import re
import tempfile
from typing import Any

import requests
from decouple import config
from faster_whisper import WhisperModel

from download.r2_storage import download_file_from_r2, upload_string_to_r2


def _strip_json_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```json"):
        s = s[7:]
    if s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def _auto_device() -> str:
    forced = (config("WHISPER_DEVICE", default="") or "").strip().lower()
    if forced in {"cpu", "cuda"}:
        return forced

    try:
        import ctranslate2

        if getattr(ctranslate2, "get_cuda_device_count", None) and ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass

    return "cpu"


def transcrever_audio(
    audio_path: str,
    *,
    model_size: str | None = None,
    fallback_model_size: str | None = None,
) -> list[dict[str, Any]]:
    model_size = (model_size or config("WHISPER_MODEL", default="medium")).strip() or "medium"
    fallback_model_size = (fallback_model_size or config("WHISPER_FALLBACK_MODEL", default="small")).strip() or "small"

    device = _auto_device()
    compute_type = "float16" if device == "cuda" else "int8"

    last_error: Exception | None = None
    for size in [model_size, fallback_model_size]:
        try:
            model = WhisperModel(size, device=device, compute_type=compute_type)
            segments, _info = model.transcribe(
                audio_path,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                word_timestamps=False,
                beam_size=5,
                best_of=5,
                language=None,
            )
            out: list[dict[str, Any]] = []
            for seg in segments:
                out.append(
                    {
                        "start": float(seg.start),
                        "end": float(seg.end),
                        "text": (seg.text or "").strip(),
                    }
                )
            return out
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Falha ao transcrever com faster-whisper (tentativas: {model_size}, {fallback_model_size})") from last_error


def _build_transcript_text(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for s in segments:
        start = float(s.get("start") or 0.0)
        end = float(s.get("end") or 0.0)
        text = (s.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{start:.2f}-{end:.2f}: {text}")
    return "\n".join(lines).strip()


def _ollama_base_url() -> str:
    base = (config("OLLAMA_BASE_URL", default="http://localhost:11434") or "").strip().rstrip("/")
    if not base.startswith("http://localhost") and not base.startswith("http://127.0.0.1"):
        raise ValueError("OLLAMA_BASE_URL deve apontar para localhost (offline).")
    return base


def gerar_cortes_virais_ollama(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_url = _ollama_base_url()
    model = (config("OLLAMA_MODEL", default="llama3:8b") or "").strip() or "llama3:8b"

    prompt = (
        "Analise a transcrição abaixo e identifique os melhores trechos para cortes virais (TikTok/Reels). Priorize:\n\n"
        "momentos engraçados\n"
        "frases impactantes\n"
        "viradas inesperadas (plot twist)\n"
        "falas emocionais ou polêmicas\n\n"
        "Retorne SOMENTE em JSON válido no formato:\n\n"
        "[\n"
        "{\n"
        '"titulo_viral": "...",\n'
        '"timestamp_inicio": "MM",\n'
        '"duracao_segundos": 30-60,\n'
        '"transcricao": "...",\n'
        '"motivo_viral": "..."\n'
        "}\n"
        "]\n"
    )

    transcript_text = _build_transcript_text(segments)
    if not transcript_text:
        return []

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Você é um editor de vídeos especialista em cortes virais."},
            {"role": "user", "content": f"{prompt}\n\nTranscrição:\n{transcript_text}"},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.4},
    }

    resp = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=float(config("OLLAMA_TIMEOUT", default="120")),
    )
    resp.raise_for_status()
    data = resp.json()

    content = ""
    msg = data.get("message") or {}
    if isinstance(msg, dict):
        content = msg.get("content") or ""
    if not content and "response" in data:
        content = data.get("response") or ""

    content = _strip_json_fences(content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"(\[\s*{[\s\S]*}\s*\])", content)
        if not m:
            raise ValueError("Ollama não retornou JSON válido.")
        parsed = json.loads(m.group(1))

    if not isinstance(parsed, list):
        raise ValueError("Ollama retornou JSON inválido (esperado lista).")

    return parsed


def processar_audio_offline(r2_audio_key: str, r2_prefix: str = "", video_id: str = "offline_result") -> str:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_audio_path = os.path.join(temp_dir, "voice.mp3")

        if not download_file_from_r2(r2_audio_key, temp_audio_path):
            raise RuntimeError(f"Falha ao baixar áudio {r2_audio_key} do R2")
        if not os.path.exists(temp_audio_path):
            raise RuntimeError("Arquivo de áudio não foi baixado corretamente")

        segments = transcrever_audio(temp_audio_path)
        cortes = gerar_cortes_virais_ollama(segments)

        json_resultado = json.dumps(cortes, ensure_ascii=False)
        json_key = f"{r2_prefix}{video_id}.json" if r2_prefix else f"{video_id}.json"
        if not upload_string_to_r2(json_resultado, json_key):
            raise RuntimeError(f"Falha ao salvar JSON no R2: {json_key}")

        return json_resultado

