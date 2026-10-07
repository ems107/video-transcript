"""Publica una nueva versión: actualiza números de versión, CHANGELOG, commit y tag.

Uso (desde la raíz del repositorio):

    python scripts/release.py patch|minor|major [--push] [--dry-run]
    python scripts/release.py 1.2.0 [--push]

Pasos:
1. Comprueba que el árbol de trabajo está limpio, que estás en `main` y que la sección
   «Sin publicar» del CHANGELOG tiene contenido.
2. Calcula la nueva versión (SemVer) y la escribe en VERSION, backend/pyproject.toml,
   backend/uv.lock, frontend/package.json y frontend/package-lock.json.
3. Convierte «Sin publicar» en «[X.Y.Z] - AAAA-MM-DD» y actualiza los enlaces de comparación.
4. Crea el commit «Versión X.Y.Z» y el tag anotado vX.Y.Z con las notas de la versión.
5. Con --push: sube main y el tag a GitHub y crea la release con `gh` (si está instalado).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
UNRELEASED = "## [Sin publicar]"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git(*args: str, capture: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, encoding="utf-8",
                       capture_output=capture)
    return (r.stdout or "").strip()


def fail(msg: str) -> None:
    sys.exit(f"Error: {msg}")


def next_version(current: str, bump: str) -> str:
    m = SEMVER.match(current)
    if not m:
        fail(f"VERSION no es SemVer: {current!r}")
    major, minor, patch = map(int, m.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if not SEMVER.match(bump):
        fail(f"versión no válida: {bump!r} (usa patch, minor, major o X.Y.Z)")
    if tuple(map(int, bump.split("."))) <= (major, minor, patch):
        fail(f"{bump} no es mayor que la versión actual {current}")
    return bump


def sub_once(path: Path, pattern: str, repl: str, flags: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        fail(f"no se encontró la versión en {path.relative_to(ROOT)}")
    path.write_text(new, encoding="utf-8", newline="\n")


def bump_files(new: str) -> None:
    (ROOT / "VERSION").write_text(new + "\n", encoding="utf-8", newline="\n")
    sub_once(ROOT / "backend/pyproject.toml", r'(?m)^version = "[^"]+"', f'version = "{new}"')
    sub_once(ROOT / "backend/uv.lock", r'(name = "video-transcript"\nversion = )"[^"]+"', rf'\1"{new}"')
    for name in ("package.json", "package-lock.json"):
        path = ROOT / "frontend" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = new
        if "packages" in data and "" in data["packages"]:
            data["packages"][""]["version"] = new
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def release_notes(text: str) -> str:
    start = text.index(UNRELEASED) + len(UNRELEASED)
    end = text.find("\n## [", start)
    return text[start:end if end != -1 else len(text)].split("\n[", 1)[0].strip()


def update_changelog(new: str, old: str, repo_url: str | None) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    if UNRELEASED not in text:
        fail(f"CHANGELOG.md no tiene la sección «{UNRELEASED}»")
    notes = release_notes(text)
    if not re.search(r"^\s*[-*] ", notes, flags=re.M):
        fail("la sección «Sin publicar» del CHANGELOG está vacía: describe los cambios antes de publicar")
    today = dt.date.today().isoformat()
    text = text.replace(UNRELEASED, f"{UNRELEASED}\n\n## [{new}] - {today}", 1)
    if repo_url:
        text = re.sub(r"(?m)^\[Sin publicar\]: .*$", f"[Sin publicar]: {repo_url}/compare/v{new}...HEAD", text)
        link = f"[{new}]: {repo_url}/compare/v{old}...v{new}"
        text = re.sub(r"(?m)^(\[Sin publicar\]: .*)$", rf"\1\n{link}", text, count=1)
    CHANGELOG.write_text(text, encoding="utf-8", newline="\n")
    return notes


def repo_url() -> str | None:
    try:
        url = git("remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        return None
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return f"https://github.com/{m.group(1)}" if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bump", help="patch, minor, major o una versión X.Y.Z")
    ap.add_argument("--push", action="store_true", help="subir a GitHub y crear la release")
    ap.add_argument("--dry-run", action="store_true", help="solo mostrar qué versión se publicaría")
    args = ap.parse_args()

    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    new = next_version(current, args.bump)
    tag = f"v{new}"
    print(f"{current} -> {new}")
    if args.dry_run:
        print(release_notes(CHANGELOG.read_text(encoding="utf-8")) or "(sin notas)")
        return

    if git("status", "--porcelain"):
        fail("hay cambios sin commitear; haz commit o descártalos antes de publicar")
    if git("branch", "--show-current") != "main":
        fail("las versiones se publican desde la rama main")
    if git("tag", "--list", tag):
        fail(f"el tag {tag} ya existe")

    notes = update_changelog(new, current, repo_url())
    bump_files(new)
    git("add", "VERSION", "CHANGELOG.md", "backend/pyproject.toml", "backend/uv.lock",
        "frontend/package.json", "frontend/package-lock.json")
    git("commit", "-m", f"Versión {new}")
    git("tag", "-a", tag, "--cleanup=verbatim", "-m", f"Versión {new}\n\n{notes}")
    print(f"Creado el commit y el tag {tag}.")

    if not args.push:
        print("Para publicarla: git push origin main --follow-tags  (o repite con --push)")
        return
    git("push", "origin", "main", "--follow-tags", capture=False)
    if shutil.which("gh"):
        subprocess.run(["gh", "release", "create", tag, "--title", f"v{new}", "--notes", notes],
                       cwd=ROOT, check=True)
    else:
        print("gh no está instalado: crea la release en GitHub a partir del tag si la quieres.")


if __name__ == "__main__":
    main()
