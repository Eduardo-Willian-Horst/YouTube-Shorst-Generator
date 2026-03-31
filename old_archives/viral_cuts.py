import os
import re
from typing import List, Tuple, Dict
from dotenv import load_dotenv

import numpy as np
from faster_whisper import WhisperModel


load_dotenv()

VIDEO_PATH = "new_video.mp4"
MODEL_SIZE = "medium"
EXPORT_DIR = "last_clips"

TARGET_MIN = float(os.getenv('TARGET_MIN', '20.0'))
TARGET_MAX = float(os.getenv('TARGET_MAX', '60.0'))
TOP_K = int(os.getenv('TOP_K', '10'))
DEVICE = os.getenv('DEVICE', 'cuda')

COMPUTE_TYPE = 'int8' if DEVICE == 'cpu' else 'float16'

KEYWORDS = [
    "segredo", "truque", "dica", "importante", "atenção", "chocante", "polêmico",
    "ganhar", "perder", "funciona", "não funciona", "por quê", "porque",
    "olha só", "presta atenção", "a verdade", "passo a passo", "resultado",

    "secret", "trick", "tip", "important", "attention", "shocking", "controversial",
    "works", "doesn't work", "why", "truth", "step by step", "result"
]
KW_REGEX = re.compile("|".join([re.escape(k) for k in KEYWORDS]), flags=re.IGNORECASE)


def transcribe(video_path: str, model_size: str, device: str, compute_type: str):
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        video_path,
        vad_filter=True,              
        vad_parameters=dict(min_silence_duration_ms=300),
        word_timestamps=False,        
        beam_size=5,
        best_of=5,
        language=None                 
    )
    out = []
    for seg in segments:
        out.append((float(seg.start), float(seg.end), seg.text.strip()))
    return out, info


def build_windows(segments: List[Tuple[float, float, str]],
                  target_min=TARGET_MIN,
                  target_max=TARGET_MAX) -> List[Dict]:
    
    windows = []
    n = len(segments)
    i = 0
    while i < n:
        start_i = segments[i][0]
        end_i = segments[i][1]
        text_parts = [segments[i][3-1]]
        dur = end_i - start_i
        j = i + 1

        while dur < target_min and j < n:
            end_i = segments[j][1]
            text_parts.append(segments[j][2])
            dur = end_i - start_i
            j += 1

        if dur < target_min and j >= n:
            pass

        while dur > target_max and j - 1 > i:
            j -= 1
            end_i = segments[j - 1][1]
            text_parts = [s[2] for s in segments[i:j]]
            dur = end_i - start_i

        window_text = " ".join(text_parts).strip()
        windows.append({
            "start": start_i,
            "end": end_i,
            "duration": max(0.0, end_i - start_i),
            "text": window_text
        })
        step = max(1, (j - i) // 2)
        i += step

    return windows


def score_window(win: Dict) -> float:
    text = win["text"]
    dur = max(1e-6, win["duration"]) 

    kws = KW_REGEX.findall(text)
    kw_score = min(2.0, 0.7 * len(kws))

    punct_score = 0.0
    if "?" in text:
        punct_score += 0.5
    if "!" in text:
        punct_score += 0.5

    words = re.findall(r"\w+", text, flags=re.UNICODE)
    wps = len(words) / dur
    if wps <= 1.0 or wps >= 6.0:
        wps_score = 0.0
    else:
        wps_score = 1.0 - (abs(wps - 3.0) / 2.0)
        wps_score = max(0.0, min(1.0, wps_score))

    ideal_min, ideal_max = 30.0, 45.0
    if dur < TARGET_MIN or dur > TARGET_MAX:
        len_score = 0.0
    elif dur < ideal_min:
        len_score = 0.5 * (dur - TARGET_MIN) / max(1e-6, (ideal_min - TARGET_MIN))
    elif dur > ideal_max:
        len_score = 0.5 * (TARGET_MAX - dur) / max(1e-6, (TARGET_MAX - ideal_max))
    else:
        len_score = 0.5  

    return kw_score + punct_score + wps_score + len_score


def pick_top(windows: List[Dict], k=TOP_K) -> List[Dict]:
    scores = np.array([score_window(w) for w in windows], dtype=float)
    order = np.argsort(-scores)
    out = []
    for idx in order[:k]:
        w = dict(windows[idx])
        w["score"] = float(scores[idx])
        out.append(w)
    return out


def hms(t: float) -> str:
    if t < 0: t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - 3600*h - 60*m
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def export_clips(video_path: str, clips: List[Dict], out_dir: str):

    os.makedirs(out_dir, exist_ok=True)
    import subprocess
    for i, c in enumerate(clips, 1):
        ss = c["start"]
        to = c["end"]
        out_path = os.path.join(out_dir, f"{i}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{ss:.3f}",
            "-to", f"{to:.3f}",
            "-i", video_path,
            "-c", "copy",
            out_path
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[success] Exported: {out_path}")
        except subprocess.CalledProcessError as e:
            print(f"[warning] Failed to export {out_path}: {e}")

def make_viral_cuts():
    device = DEVICE
    compute_type = COMPUTE_TYPE
    target_min = float(TARGET_MIN)
    target_max = float(TARGET_MAX)
    top_k = int(TOP_K)

    print(f"[info] Transcribing with faster-whisper (model={MODEL_SIZE}, device={device}, compute={compute_type})...")
    segments, info = transcribe(VIDEO_PATH, MODEL_SIZE, device, compute_type)
    if not segments:
        print("[error] No speech segments recognized in the video.")
        return

    print(f"[info] Detected language: {info.language}, confidence={getattr(info, 'language_probability', 0.0)*100:.1f}%")
    print(f"[info] Processed {len(segments)} speech segments.")

    windows = build_windows(segments, target_min=target_min, target_max=target_max)
    if not windows:
        print("[error] No valid video segments found with the current parameters.")
        return

    top = pick_top(windows, k=top_k)
    export_clips(VIDEO_PATH, top, EXPORT_DIR)
