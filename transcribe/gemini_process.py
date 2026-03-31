from .offline_process import processar_audio_offline


def processar_audio_com_gemini(r2_audio_key, r2_prefix="", video_id="gemini_result"):
    return processar_audio_offline(r2_audio_key, r2_prefix=r2_prefix, video_id=video_id)
