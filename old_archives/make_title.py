import os
from pathlib import Path

def read_title():
    try:
        with open('title.txt', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("[error] File 'title.txt' not found.")
        return ""

def make_title():
    titulo = read_title()
    if not titulo:
        return
    
    pasta = Path('last_clips')
    if not pasta.exists():
        print("[error] Folder 'last_clips' not found.")
        return
    
    arquivos = [f for f in pasta.iterdir() if f.is_file()]
    
    for arquivo in arquivos:
        novo_nome = f"{titulo} - {arquivo.name}"
        novo_caminho = pasta / novo_nome
        
        try:
            arquivo.rename(novo_caminho)
            print(f"[success] Renamed: {arquivo.name} -> {novo_nome}")
        except Exception as e:
            print(f"[error] Failed to rename {arquivo.name}: {e}")


