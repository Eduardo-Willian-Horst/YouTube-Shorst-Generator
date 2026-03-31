import re


def formatar_titulo_shorts(filename: str) -> str:
    base = re.sub(r"\.[a-zA-Z0-9]+$", "", filename.strip())
    base = re.sub(r"_[0-9]+$", "", base)
    base = base.replace("-", " ").replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()

    if base:
        base = base[:1].upper() + base[1:].lower()

    if " o que " in base and "." not in base:
        base = base.replace(" o que ", ". o que ", 1)

    return f"{base} #Shorts".strip()

