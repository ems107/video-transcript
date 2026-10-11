"""La ayuda de la web: valores en vivo, enlaces, anclas y capturas existen."""

import re
import unicodedata
from pathlib import Path

from app import help_values

ROOT = Path(__file__).resolve().parents[2]
HELP = ROOT / "frontend" / "src" / "help"
SHOTS = ROOT / "frontend" / "public" / "capturas"
SECTIONS = {"Empezar", "Cada vídeo", "Conocimiento", "Otros", "Por dentro", "Ayuda"}


def slugify(text: str) -> str:
    """Igual que `slugify` de frontend/src/help/index.ts."""
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", t))


def pages() -> dict[str, tuple[dict[str, str], str]]:
    out = {}
    for f in sorted(HELP.glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
        assert m, f"{f.name}: falta la cabecera"
        meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        out[f.stem] = ({k.strip(): v.strip() for k, v in meta.items()}, m.group(2))
    return out


def test_pages_have_valid_headers():
    ps = pages()
    assert len(ps) >= 15
    for slug, (meta, _) in ps.items():
        assert meta.get("titulo") and meta.get("seccion") in SECTIONS and meta.get("orden", "").isdigit(), slug


def test_live_values_exist():
    values = help_values.values()
    for slug, (_, body) in pages().items():
        for key in re.findall(r"\{\{v:([a-z0-9_]+)\}\}", body):
            assert key in values, f"{slug}: {{{{v:{key}}}}} no existe en help_values"


def test_internal_links_and_anchors():
    ps = pages()
    anchors = {slug: {slugify(h) for h in re.findall(r"^#{2,3} (.+)$", body, re.M)} for slug, (_, body) in ps.items()}
    for slug, (_, body) in ps.items():
        for page, anchor in re.findall(r"\]\(ayuda:([a-z0-9-]+)(?:#([a-z0-9-]+))?\)", body):
            assert page in ps, f"{slug}: enlace a una página que no existe: {page}"
            assert not anchor or anchor in anchors[page], f"{slug}: ancla inexistente {page}#{anchor}"


def test_technical_blocks_are_closed():
    for slug, (_, body) in pages().items():
        opens = len(re.findall(r"^:::tecnico", body, re.M))
        closes = len(re.findall(r"^:::\s*$", body, re.M))
        assert opens == closes, f"{slug}: bloques técnicos sin cerrar"


def test_screenshots_exist():
    missing = sorted({name for _, body in pages().values() for name in re.findall(r"\(captura:([a-z0-9-]+)\)", body)
                      if not (SHOTS / f"{name}.png").exists()})
    assert not missing, f"Faltan capturas (ejecuta scripts/help_screenshots.py): {missing}"
