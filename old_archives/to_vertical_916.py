import subprocess
import os
import sys
from pathlib import Path


DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_CRF = 20
DEFAULT_PRESET = "medium"
DEFAULT_INPUT_DIR = "last_clips"

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr + "\n")
        sys.exit(p.returncode)

def process_video(input_file, output_file=None, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, 
                 crf=DEFAULT_CRF, preset=DEFAULT_PRESET, remove_original=True):

    input_path = Path(input_file)
    if not output_file:
        output_file = str(input_path.with_stem(f"pt. {input_path.stem}"))

    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_file
    ]
    run(cmd)
    
    if remove_original and os.path.exists(output_file):
        try:
            os.remove(str(input_path))
        except Exception as e:
            print(f"[warning] Could not delete original file {input_path}: {e}")

def to_vertical_916():
    input_path = DEFAULT_INPUT_DIR
    
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv')
    processed_count = 0
    
    video_files = [f for f in Path(input_path).iterdir() 
                  if f.suffix.lower() in video_extensions and 
                  not f.name.startswith("pt.")]
    
    for video_file in video_files:
        print(f"[info] Processing: {video_file.name}")
        process_video(
            str(video_file),
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT,
            crf=DEFAULT_CRF,
            preset=DEFAULT_PRESET,
            remove_original=True
        )
        processed_count += 1
    
    if processed_count == 0:
        print(f"[info] No video files found in: {input_path}")
    else:
        print(f"[success] Processing completed! {processed_count} video(s) processed.")



