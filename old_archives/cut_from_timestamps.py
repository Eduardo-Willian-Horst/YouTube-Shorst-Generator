# cut_from_timestamps.py
import argparse, subprocess, os, sys, csv

def hms_ok(s: str) -> bool:
    # formatos aceitos: H:MM:SS, HH:MM:SS, com ou sem milissegundos (ex: 00:00:12.345)
    return len(s.split(":")) in (2,3)

def main():
    ap = argparse.ArgumentParser(description="Corta clipes a partir de um arquivo de timestamps.")
    ap.add_argument("video", help="Arquivo de vídeo (ex: input.mp4)")
    ap.add_argument("timestamps", help="Arquivo texto/CSV com linhas: start,end[,label]")
    ap.add_argument("--outdir", default="clips", help="Pasta de saída (default: clips)")
    ap.add_argument("--reencode", action="store_true",
                    help="Faz reencode (preciso no frame, porém mais lento).")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    rows = []
    with open(args.timestamps, "r", encoding="utf-8") as f:
        # aceita CSV ou txt com vírgula
        reader = csv.reader((line for line in f if line.strip()))
        for line_no, cols in enumerate(reader, start=1):
            if len(cols) < 2:
                print(f"[linha {line_no}] ignorada (faltam start,end): {cols}")
                continue
            start, end = cols[0].strip(), cols[1].strip()
            label = cols[2].strip() if len(cols) >= 3 and cols[2].strip() else None
            if not (hms_ok(start) and hms_ok(end)):
                print(f"[linha {line_no}] formato inválido de tempo: {cols}")
                continue
            rows.append((start, end, label))

    if not rows:
        print("Nenhum corte válido encontrado no arquivo de timestamps.")
        sys.exit(1)

    for i, (start, end, label) in enumerate(rows, 1):
        base = label if label else f"clip_{i:02d}"
        # limpa caracteres problemáticos para nome de arquivo no Windows
        safe = "".join(c for c in base if c not in '\\/:*?"<>|').strip() or f"clip_{i:02d}"
        out = os.path.join(args.outdir, f"{safe}.mp4")

        if args.reencode:
            # Corte preciso (frame-accurate): -ss depois do -i e reencode
            cmd = [
                "ffmpeg", "-y",
                "-i", args.video,
                "-ss", start, "-to", end,
                "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
                out
            ]
        else:
            # Rápido, sem reencode (pode iniciar levemente antes do start)
            # -ss antes do -i é mais rápido; -to define o ponto final relativo ao início original
            cmd = [
                "ffmpeg", "-y",
                "-ss", start, "-to", end,
                "-i", args.video,
                "-c", "copy",
                out
            ]

        print("Executando:", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[ok] {out}")
        except subprocess.CalledProcessError as e:
            print(f"[falhou] {out}: {e}")

if __name__ == "__main__":
    main()
