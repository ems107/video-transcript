"""Lógica pura de los seguimientos: estado de cada punto, contexto para la IA, aplicar y deshacer vídeos.

Un punto (tarea, decisión o duda) tiene un recorrido de eventos, cada uno con su vídeo y su momento.
Su estado sale siempre del último evento que lo cambia. Lo que hace el usuario es «manual»: la IA puede
añadir avances al recorrido de un punto manual, pero nunca cambia su texto ni su estado.

Los puntos son diccionarios `{id, kind, text, owner, due, status, manual, hidden, events}`. Cada evento
guarda la fecha de grabación de su vídeo: así el estado se entiende aunque el vídeo se quite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from .knowledge import parse_ts
from .pipeline.glossary import normalize
from .pipeline.transcript import fmt_ts

KINDS = ("tarea", "decision", "duda")
PREFIX = {"tarea": "T", "decision": "D", "duda": "P"}
KIND_LABELS = {"tarea": "Tareas", "decision": "Decisiones", "duda": "Dudas y pendientes"}
INITIAL = {"tarea": "abierta", "decision": "vigente", "duda": "abierta"}
# Evento -> estado en que deja el punto («avanza» no lo cambia)
EVENT_STATUS = {
    "tarea": {"hecha": "hecha", "descartada": "descartada", "reabierta": "abierta"},
    "decision": {"cambiada": "cambiada", "anulada": "anulada", "reabierta": "vigente"},
    "duda": {"resuelta": "resuelta", "reabierta": "abierta"},
}
STATUSES = {k: [INITIAL[k], *(s for s in dict.fromkeys(v.values()) if s != INITIAL[k])] for k, v in EVENT_STATUS.items()}
OPEN = {"tarea": {"abierta"}, "decision": {"vigente"}, "duda": {"abierta"}}
EVENT_LABELS = {"creada": "aparece", "avanza": "avanza", "hecha": "hecha", "descartada": "descartada",
                "reabierta": "reabierta", "cambiada": "cambiada", "anulada": "anulada", "resuelta": "resuelta"}

# Máximo de caracteres del estado que recibe la IA como contexto. Lo abierto va primero; si no cabe, se
# recorta lo ya cerrado. Con unos pocos vídeos sobra: es un tope para que un seguimiento largo no se coma
# el contexto del modelo.
FOLLOW_CONTEXT_CHARS = 8000
RECENT_VIDEOS = 2  # lo cerrado en los últimos vídeos se sigue mostrando
DUPLICATE = 85  # parecido (0-100) a partir del cual un punto nuevo repite uno existente
T_TOLERANCE = 5.0  # segundos de margen al comprobar que el momento está dentro del vídeo


def short_id(item: dict[str, Any]) -> str:
    return f"{PREFIX[item['kind']]}{item['id']}"


def derive_status(kind: str, events: list[dict[str, Any]]) -> str:
    status = INITIAL[kind]
    for e in events:
        status = EVENT_STATUS[kind].get(e["evento"], status)
    return status


def status_for_event(kind: str, status: str) -> str | None:
    """Evento que deja el punto en ese estado (para los cambios manuales)."""
    if status == INITIAL[kind]:
        return "reabierta"
    return next((ev for ev, st in EVENT_STATUS[kind].items() if st == status), None)


def event_date(e: dict[str, Any]) -> datetime | None:
    return datetime.fromisoformat(e["date"]) if e.get("date") else None


def state_at(items: list[dict[str, Any]], before: datetime | None) -> list[dict[str, Any]]:
    """Los puntos tal como estaban antes de esa fecha: solo cuenta lo que dijeron los vídeos anteriores.

    Lo manual cuenta siempre: es lo que el usuario sabe ahora. Los puntos borrados no se muestran."""
    out = []
    for it in items:
        if it.get("hidden"):
            continue
        evs = [e for e in it["events"] if e.get("source") == "manual" or before is None
               or ((d := event_date(e)) is not None and d < before)]
        if not evs or (not it.get("manual") and evs[0]["evento"] != "creada"):
            continue
        out.append({**it, "events": evs, "status": derive_status(it["kind"], evs)})
    return out


def _created(it: dict[str, Any]) -> str:
    d = next((event_date(e) for e in it["events"] if event_date(e)), None)
    return d.strftime("%Y-%m-%d") if d else ""


def _line(it: dict[str, Any], with_ids: bool) -> str:
    created = _created(it)
    extra = [x for x in (f"responsable: {it['owner']}" if it.get("owner") else "",
                         f"plazo: {it['due']}" if it.get("due") else "",
                         f"desde el {created}" if created else "") if x]
    notes = [e["nota"] for e in it["events"][1:] if e.get("nota")][-2:]
    text = ("[" + short_id(it) + "] " if with_ids else "") + it["text"]
    if extra:
        text += f" ({'; '.join(extra)})"
    if notes:
        text += " — " + " / ".join(notes)
    return "- " + text


def context_block(name: str, description: str, summary: str, items: list[dict[str, Any]],
                  video_dates: list[datetime], before: datetime | None, with_ids: bool = False,
                  max_chars: int = FOLLOW_CONTEXT_CHARS) -> str:
    """El estado del seguimiento antes de esa fecha, en texto para la IA."""
    state = state_at(items, before)
    previous = sorted(d for d in video_dates if before is None or d < before)
    if not previous and not state:
        return ""
    recent = set(previous[-RECENT_VIDEOS:])
    head = [f"Seguimiento «{name}»" + (f": {description}" if description else "")]
    if previous:
        head.append(f"Vídeos anteriores del tema: {len(previous)}, del {previous[0]:%Y-%m-%d} al {previous[-1]:%Y-%m-%d}.")
    if summary:
        head.append("Resumen de la evolución hasta ahora:\n" + summary.strip())
    sections: list[tuple[str, list[str]]] = []
    for kind in KINDS:
        rows = [it for it in state if it["kind"] == kind and it["status"] in OPEN[kind]]
        if rows:
            label = {"tarea": "Tareas abiertas", "decision": "Decisiones vigentes", "duda": "Dudas abiertas"}[kind]
            sections.append((label, [_line(it, with_ids) for it in rows]))
    closed = []
    for it in state:
        if it["status"] in OPEN[it["kind"]]:
            continue
        last = it["events"][-1]
        d = event_date(last)
        if last.get("source") == "manual" or (d and d in recent):
            closed.append(_line(it, with_ids) + f" [{it['status']}]")
    if closed:
        sections.append(("Cerrado recientemente", closed))

    out = "\n".join(head)
    for label, rows in sections:
        block, left = "\n" + label + ":", len(rows)
        for r in rows:
            if len(out) + len(block) + len(r) + 1 > max_chars:
                break
            block += "\n" + r
            left -= 1
        if left:
            block += f"\n- (…y {left} más)"
        out += block
    return out


def _valid_t(t: str, duration: float) -> float | None:
    s = parse_ts(t or "")
    return s if s is not None and s <= duration + T_TOLERANCE else None


def _similar(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(normalize(a), normalize(b)) >= DUPLICATE


def apply_update(items: list[dict[str, Any]], update: dict[str, Any], video_id: int, video_date: datetime,
                 duration: float, at: datetime) -> dict[str, Any]:
    """Valida la respuesta de la IA para un vídeo y devuelve qué cambiar.

    Devuelve `{"events": [(item_id, evento)], "new": [punto], "discarded": [motivo]}`. Se descartan las
    referencias a puntos que no existen, los momentos que no están en el vídeo, los cambios de estado no
    válidos para el tipo de punto y los puntos nuevos que repiten uno existente."""
    by_id = {short_id(it): it for it in items}
    events, new, discarded = [], [], []
    seen: set[tuple[int, str]] = set()
    for e in update.get("eventos") or []:
        it = by_id.get(str(e.get("id", "")).strip().strip("[]").upper())
        t = _valid_t(e.get("t", ""), duration)
        evento = e.get("evento", "")
        if not it or it.get("hidden"):
            discarded.append(f"{e.get('id')}: no existe")
            continue
        if t is None:
            discarded.append(f"{e.get('id')}: momento fuera del vídeo ({e.get('t')})")
            continue
        if evento != "avanza" and evento not in EVENT_STATUS[it["kind"]]:
            discarded.append(f"{e.get('id')}: «{evento}» no vale para una {it['kind']}")
            continue
        nota = (e.get("nota") or "").strip()
        if it.get("manual") and evento != "avanza":
            # Lo decidió el usuario: el vídeo solo se anota como avance
            nota, evento = f"(el vídeo dice: {evento}) {nota}".strip(), "avanza"
        if (it["id"], evento) in seen:
            continue
        seen.add((it["id"], evento))
        events.append((it["id"], {"video_id": video_id, "date": video_date.isoformat(), "t": fmt_ts(t),
                                  "evento": evento, "nota": nota, "source": "ia", "at": at.isoformat()}))
    existing = [(it["kind"], it["text"]) for it in items]
    for n in update.get("nuevos") or []:
        kind, text = n.get("tipo", ""), (n.get("texto") or "").strip()
        t = _valid_t(n.get("t", ""), duration)
        if kind not in KINDS or not text:
            continue
        if t is None:
            discarded.append(f"nuevo «{text}»: momento fuera del vídeo ({n.get('t')})")
            continue
        if any(k == kind and _similar(text, other) for k, other in existing):
            discarded.append(f"nuevo «{text}»: ya existe")
            continue
        existing.append((kind, text))
        new.append({"kind": kind, "text": text, "owner": (n.get("responsable") or "").strip(),
                    "due": (n.get("plazo") or "").strip(), "status": INITIAL[kind], "manual": False,
                    "hidden": False,
                    "events": [{"video_id": video_id, "date": video_date.isoformat(), "t": fmt_ts(t),
                                "evento": "creada", "nota": "", "source": "ia", "at": at.isoformat()}]})
    return {"events": events, "new": new, "discarded": discarded}


def revert(items: list[dict[str, Any]], video_ids: set[int]) -> dict[str, Any]:
    """Qué deshacer para quitar del estado lo que la IA sacó de esos vídeos.

    Devuelve `{"delete": [ids], "update": {id: eventos}}`. Los puntos que la IA creó en esos vídeos se
    borran, salvo que el usuario los haya tocado; de los demás se quitan los eventos de la IA de esos
    vídeos. Lo manual se conserva siempre."""
    delete, update = [], {}
    for it in items:
        evs = it["events"]
        from_ia = [e for e in evs if e.get("source") != "manual" and e.get("video_id") in video_ids]
        if not from_ia:
            continue
        created_here = evs and evs[0] in from_ia and evs[0]["evento"] == "creada"
        if created_here and not it.get("manual"):
            delete.append(it["id"])
            continue
        update[it["id"]] = [e for e in evs if e not in from_ia or (e is evs[0] and e["evento"] == "creada")]
    return {"delete": delete, "update": update}


def analysis_text(a: dict[str, Any], max_chars: int = 12000) -> str:
    """Lo que la IA necesita del análisis de un vídeo para actualizar el seguimiento."""
    parts = []
    if a.get("resumen_breve"):
        parts.append("Resumen breve:\n" + a["resumen_breve"])
    if a.get("resumen_detallado"):
        parts.append("Resumen detallado:\n" + a["resumen_detallado"][:max_chars])
    if a.get("tareas"):
        parts.append("Tareas:\n" + "\n".join(
            f"- [{x.get('t', '')}] {x.get('tarea', '')}" + (f" (responsable: {x['responsable']})" if x.get("responsable") else "")
            + (f" (plazo: {x['plazo']})" if x.get("plazo") else "") for x in a["tareas"]))
    if a.get("decisiones"):
        parts.append("Decisiones:\n" + "\n".join(f"- [{x.get('t', '')}] {x.get('decision', '')}" for x in a["decisiones"]))
    if a.get("pendientes"):
        parts.append("Pendientes:\n" + "\n".join(f"- {x}" for x in a["pendientes"]))
    return "\n\n".join(parts)


def render_markdown(f: dict[str, Any], items: list[dict[str, Any]], videos: list[dict[str, Any]]) -> str:
    """Documento `seguimiento.md` de la carpeta del seguimiento.

    `videos`: `[{id, title, date, link, contribution, applied}]` en orden de fecha; `link` es la ruta
    relativa a su carpeta o «»."""
    by_id = {v["id"]: v for v in videos}

    def where(e: dict[str, Any]) -> str:
        v = by_id.get(e.get("video_id"))
        d = event_date(e)
        if not d:
            return "a mano" if e.get("source") == "manual" else ""
        label = f"{d:%Y-%m-%d}" + (f" {e['t']}" if e.get("t") else "")
        return f"[{label}]({v['link']}/resumen.md)" if v and v.get("link") else label

    out = [f"# Seguimiento: {f['name']}", ""]
    if f.get("description"):
        out += [f["description"], ""]
    if videos:
        out += [f"- **Vídeos:** {len(videos)}, del {videos[0]['date']:%Y-%m-%d} al {videos[-1]['date']:%Y-%m-%d}"]
    if f.get("stale_from"):
        out += [f"- **Aviso:** el estado no está al día desde el {f['stale_from']:%Y-%m-%d}. {f.get('stale_reason', '')}"]
    out.append("")
    if f.get("summary"):
        out += ["## Resumen", "", f["summary"].strip(), ""]
    shown = [it for it in items if not it.get("hidden")]
    for kind in KINDS:
        rows = [it for it in shown if it["kind"] == kind]
        if not rows:
            continue
        out += [f"## {KIND_LABELS[kind]}", ""]
        for status in STATUSES[kind]:
            for it in (r for r in rows if r["status"] == status):
                who = f" — {it['owner']}" if it.get("owner") else ""
                due = f" (plazo: {it['due']})" if it.get("due") else ""
                out.append(f"- **[{status}]** {it['text']}{who}{due}")
                for e in it["events"]:
                    note = f": {e['nota']}" if e.get("nota") else ""
                    w = where(e)
                    out.append(f"  - {EVENT_LABELS.get(e['evento'], e['evento'])}{(' · ' + w) if w else ''}{note}")
        out.append("")
    if videos:
        out += ["## Vídeos", ""]
        for v in videos:
            title = f"[{v['title']}]({v['link']}/resumen.md)" if v.get("link") else v["title"]
            out.append(f"- **{v['date']:%Y-%m-%d}** · {title}" + ("" if v.get("applied") else " *(sin aplicar)*"))
            if v.get("contribution"):
                out.append(f"  - {v['contribution']}")
        out.append("")
    return "\n".join(out)
