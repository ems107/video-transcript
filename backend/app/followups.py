"""Lógica pura de los seguimientos: estado de cada punto, contexto para la IA, aplicar y deshacer vídeos.

Un punto (tarea, decisión o duda) tiene un recorrido de eventos, cada uno con su vídeo y su momento.
Su estado sale siempre del último evento que lo cambia. Lo que hace el usuario es «manual»: la IA puede
añadir avances al recorrido de un punto manual, pero nunca cambia su texto ni su estado.

Los puntos son diccionarios `{id, kind, text, owner, due, status, manual, hidden, events}`. Cada evento
guarda la fecha de grabación de su vídeo: así el estado se entiende aunque el vídeo se quite.
"""

from __future__ import annotations

import re
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


def open_possible(it: dict[str, Any]) -> dict[str, Any] | None:
    """El último cambio «posible» (sin frase que lo demuestre) que el usuario aún no ha confirmado ni descartado."""
    for e in reversed(it["events"]):
        if e.get("posible"):
            done = it["status"] == EVENT_STATUS[it["kind"]].get(e["posible"]) or e.get("descartado")
            return None if done else e
    return None


def needs_review(it: dict[str, Any], video_id: int | None = None) -> list[str]:
    """Lo que el usuario debe decidir de un punto: si duplica otro («duplicado») o si un cambio de estado sin
    frase que lo demuestre es cierto («posible»). Con `video_id`, solo lo que salió de ese vídeo."""
    if it.get("hidden"):
        return []
    out = []
    created = it["events"][0].get("video_id") if it["events"] else None
    if it.get("review") and (video_id is None or created == video_id):
        out.append(it["review"].get("tipo", "duplicado"))
    e = open_possible(it)
    if e and (video_id is None or e.get("video_id") == video_id):
        out.append("posible")
    return out


def event_date(e: dict[str, Any]) -> datetime | None:
    return datetime.fromisoformat(e["date"]) if e.get("date") else None


def sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recorrido en orden: los hitos de un vídeo por su fecha de grabación y momento; los cambios manuales,
    por cuándo los hiciste. Así el último es siempre el más reciente y manda en el estado."""
    def key(e: dict[str, Any]) -> tuple[datetime, str]:
        d = event_date(e) or datetime.fromisoformat(e["at"])
        return d, e.get("t") or ""
    creation = [e for e in events[:1] if e["evento"] == "creada"]
    return creation + sorted(events[len(creation):], key=key)


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
        # El vídeo que lo creó se conserva aunque sea este mismo (sus hitos quedan fuera del estado anterior)
        out.append({**it, "events": evs, "status": derive_status(it["kind"], evs),
                    "created_video": it["events"][0].get("video_id") if it["events"] else None})
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


# --------------------------------------------------------------------------- citas

QUOTE_SIMILAR = 85  # parecido (0-100) de la cita con lo dicho alrededor de su momento
QUOTE_WINDOW = 60.0  # segundos alrededor de la marca de tiempo en los que se busca la cita
QUOTE_MIN_CHARS = 12  # una cita más corta («sí», «vale») podría estar en cualquier parte


def quoted(cita: str, utts: list[dict[str, Any]], t: float) -> bool:
    """¿Se dice de verdad esa frase cerca de ese momento? Así un cambio de estado no se puede inventar.

    La IA a veces junta trozos con «…»: cada trozo debe decirse cerca de ese momento."""
    pieces = [normalize(x) for x in re.split(r"\.\.\.|…", cita)]
    pieces = [x for x in pieces if len(x) >= 8]
    if not pieces or max(len(x) for x in pieces) < QUOTE_MIN_CHARS:
        return False
    near = normalize(" ".join(u["text"] for u in utts if abs(u["start"] - t) <= QUOTE_WINDOW))
    return bool(near) and all(fuzz.partial_ratio(x, near) >= QUOTE_SIMILAR for x in pieces)


def check_signals(signals: list[dict[str, Any]], utts: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    """Menciones de la IA («de este punto se habla aquí»), con `verified` si la cita se dice de verdad en ese
    momento. Se descartan los ids mal formados, los momentos fuera del vídeo, las repetidas y los avances sin
    cita comprobada (no aportan nada); un cambio de estado sin cita comprobada queda como posible."""
    out, seen = [], set()
    for x in signals:
        pid = str(x.get("id", "")).strip().strip("[]").upper()
        t = _valid_t(x.get("t", ""), duration)
        evento = x.get("evento", "avanza")
        if not re.fullmatch(r"[TDP]\d+", pid) or t is None or (pid, evento) in seen:
            continue
        cita = (x.get("cita") or "").strip().strip('"«»“”')
        ok = quoted(cita, utts, t)
        if evento == "avanza" and not ok:
            continue
        seen.add((pid, evento))
        out.append({"id": pid, "evento": evento, "t": fmt_ts(t), "cita": cita, "verified": ok})
    return out


_ID_RE = re.compile(r"\s*[(\[][TDPN]\d+[)\]]")


def strip_ids(text: str) -> str:
    """Quita los identificadores internos («[T3]», «(P19)») que la IA deje en el resumen."""
    return _ID_RE.sub("", text or "").strip()


# --------------------------------------------------------------------------- puntos del vídeo

_NO_DUE = {"", "sin especificar", "no especificado", "no consta", "ninguno", "sin plazo", "no se indica"}


def pending_parts(x: Any) -> tuple[str, str]:
    """(texto, momento) de un pendiente del análisis (antes eran solo texto)."""
    return (x, "") if isinstance(x, str) else (x.get("pendiente", ""), x.get("t", ""))


def analysis_points(a: dict[str, Any]) -> list[dict[str, Any]]:
    """Las tareas, decisiones y pendientes del análisis del vídeo, con una clave [N…] para relacionarlos.

    Son los puntos nuevos del seguimiento: salen del análisis tal cual (lo que el usuario ve en el vídeo),
    no de una segunda respuesta de la IA, que variaba en cada ejecución."""
    out = []
    for x in a.get("tareas") or []:
        due = (x.get("plazo") or "").strip()
        if normalize(due) in _NO_DUE or parse_ts(due) is not None:
            due = ""  # a veces llega la marca de tiempo o «sin especificar»
        out.append({"kind": "tarea", "text": x.get("tarea", ""), "owner": x.get("responsable", ""), "due": due,
                    "t": x.get("t", "")})
    for x in a.get("decisiones") or []:
        out.append({"kind": "decision", "text": x.get("decision", ""), "owner": "", "due": "", "t": x.get("t", "")})
    for x in a.get("pendientes") or []:
        text, t = pending_parts(x)
        out.append({"kind": "duda", "text": text, "owner": "", "due": "", "t": t})
    out = [{**x, "text": x["text"].strip(), "owner": (x["owner"] or "").strip()} for x in out if x["text"].strip()]
    return [{**x, "key": f"N{i + 1}"} for i, x in enumerate(out)]


_OWNER_SEP = re.compile(r"\s*(?:[,/;]|\by\b|\be\b)\s*", re.IGNORECASE)
_OWNER_GROUP = re.compile(r"^(.*?)\((.*)\)\s*$")


def normalize_owner(owner: str, people: list[dict[str, Any]]) -> str:
    """El responsable con el nombre de las personas conocidas («Iosu/Selu» → «Iosu Urcelay, José Luis Pérez»).

    `people`: [{id, name, aliases}]. Lo que no es una persona conocida se queda como está («el proveedor»).
    En «Grupo X (A/B)», si dentro del paréntesis hay personas, el texto de fuera es solo el nombre del grupo."""
    from .pipeline.voice import match_name

    owner = (owner or "").strip()
    if not owner or not people:
        return owner
    by_id = {p["id"]: p["name"] for p in people}

    def resolve(text: str) -> list[tuple[str, bool]]:
        parts = [x.strip(" .") for x in _OWNER_SEP.split(text) if x and x.strip(" .")]
        out = []
        for x in parts:
            pid = match_name(x, people)
            out.append((by_id[pid], True) if pid is not None else (x, False))
        return out

    m = _OWNER_GROUP.match(owner)
    if m:
        inner = resolve(m.group(2))
        names = inner if inner and any(ok for _, ok in inner) else [*resolve(m.group(1)), *inner]
    else:
        names = resolve(owner)
    if not any(ok for _, ok in names):
        return owner
    seen, out = set(), []
    for name, _ in names:
        if normalize(name) not in seen:
            seen.add(normalize(name))
            out.append(name)
    return ", ".join(out)


def apply_update(items: list[dict[str, Any]], update: dict[str, Any], video_id: int, video_date: datetime,
                 duration: float, at: datetime, points: list[dict[str, Any]],
                 signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Qué cambia en el estado con un vídeo.

    Devuelve `{"events": [(item_id, evento)], "new": [punto], "discarded": [motivo]}`.
    - Hitos: salen de las menciones comprobadas (`check_signals`). Un cambio de estado con cita que se dice de
      verdad se aplica; sin ella queda como avance con `posible` (lo confirma el usuario). Se descartan los
      puntos que no existen, los cambios que no valen para el tipo de punto y los avances en el mismo vídeo en
      que aparece el punto. A un punto manual solo se le anotan avances.
    - Puntos nuevos: todos los `points` del análisis del vídeo, salvo los que la IA da por el mismo asunto que
      uno anterior («clasificacion» en `update`, que también ve los borrados por el usuario) y los que casi
      repiten el texto de uno existente. Los «dudosos» se crean con `review`, para que decida el usuario."""
    by_id = {short_id(it): it for it in items}
    events, new, discarded = [], [], []
    changes = {x["id"] for x in signals if x["evento"] != "avanza" and x["verified"]}
    seen: set[tuple[int, str, str]] = set()
    for x in signals:
        it = by_id.get(x["id"])
        evento, t = x["evento"], parse_ts(x["t"]) or 0.0
        if not it or it.get("hidden"):
            discarded.append(f"{x['id']}: no existe")
            continue
        if evento != "avanza" and evento not in EVENT_STATUS[it["kind"]]:
            discarded.append(f"{x['id']}: «{evento}» no vale para una {it['kind']}")
            continue
        created = it.get("created_video", it["events"][0].get("video_id") if it["events"] else None)
        created_here = created is not None and created == video_id
        if evento == "avanza" and (x["id"] in changes or created_here):
            continue  # ya cambia de estado en este vídeo, o es el vídeo en que aparece
        nota, possible = "", ""
        if evento != "avanza" and not x["verified"]:
            # Sin una frase que lo demuestre, el cambio queda como posible: lo confirma el usuario
            possible, evento = evento, "avanza"
        elif it.get("manual") and evento != "avanza":
            # Lo decidió el usuario: el vídeo solo se anota como avance
            if created_here:
                continue  # el vídeo que creó el punto no es un avance suyo
            nota, evento = f"El vídeo dice: {EVENT_LABELS.get(evento, evento)}.", "avanza"
        if (it["id"], evento, possible) in seen:
            continue
        seen.add((it["id"], evento, possible))
        ev = {"video_id": video_id, "date": video_date.isoformat(), "t": fmt_ts(t), "evento": evento, "nota": nota,
              "cita": x["cita"] if x["verified"] else "", "source": "ia", "at": at.isoformat()}
        if possible:
            ev["posible"] = possible
            ev["nota"] = f"Según la IA: «{x['cita']}»" if x["cita"] else ""
        events.append((it["id"], ev))
    by_key = {pt["key"]: pt for pt in points}
    verdict = classify(update, by_id, by_key)
    existing = [(it["kind"], it["text"]) for it in items]
    skipped: set[str] = set()
    created: dict[str, dict[str, Any]] = {}  # punto nuevo creado por cada [N…]
    owners_for: dict[str, list[str]] = {}  # responsables de los [N…] que se unen a otro de este vídeo

    def join_owner(target: dict[str, Any] | None, key: str | None, owner: str) -> None:
        """La misma tarea encargada a varias personas en este vídeo queda como un punto con todas ellas."""
        if not owner:
            return
        if target is None:
            owners_for.setdefault(key or "", []).append(owner)
        elif normalize(owner) not in {normalize(o) for o in target["owner"].split(", ") if o}:
            target["owner"] = ", ".join(x for x in (target["owner"], owner) if x)

    for pt in points:
        relation, other, motivo = verdict.get(pt["key"], ("nuevo", None, ""))
        if relation == "mismo" and other not in skipped:  # si los dos se dan por «el mismo», queda uno
            skipped.add(pt["key"])
            if other in by_key:
                join_owner(created.get(other), other, pt["owner"])
            discarded.append(f"{pt['key']} «{pt['text']}»: el mismo que {other}")
            continue
        # Red de seguridad: casi el mismo texto que un punto existente (también uno borrado por el usuario)
        twin = next((n for n in new if n["kind"] == pt["kind"] and _similar(pt["text"], n["text"])), None)
        if twin is not None or any(k == pt["kind"] and _similar(pt["text"], txt) for k, txt in existing):
            if twin is not None:
                join_owner(twin, None, pt["owner"])
            discarded.append(f"{pt['key']} «{pt['text']}»: ya existe")
            continue
        existing.append((pt["kind"], pt["text"]))
        t = _valid_t(pt["t"], duration)
        review: dict[str, Any] = {}
        if relation == "dudoso" and other:
            target = by_id.get(other)
            review = {"tipo": "duplicado", "de": target["id"] if target else None,
                      "texto": target["text"] if target else by_key[other]["text"], "motivo": motivo}
        item = {"kind": pt["kind"], "text": pt["text"], "owner": pt["owner"], "due": pt["due"],
                "status": INITIAL[pt["kind"]], "manual": False, "hidden": False, "review": review,
                "events": [{"video_id": video_id, "date": video_date.isoformat(), "t": fmt_ts(t) if t is not None else "",
                            "evento": "creada", "nota": "", "source": "ia", "at": at.isoformat()}]}
        for o in owners_for.pop(pt["key"], []):
            join_owner(item, None, o)
        created[pt["key"]] = item
        new.append(item)
    return {"events": events, "new": new, "discarded": discarded}


def _ref(x: Any) -> str:
    return str(x or "").strip().strip("[]").upper()


def classify(update: dict[str, Any], by_id: dict[str, dict[str, Any]],
             by_key: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str | None, str]]:
    """Qué dice la IA de cada punto del vídeo: `{N…: (mismo|nuevo|dudoso, id con el que lo compara, motivo)}`.

    Se descartan las comparaciones con un id que no existe (o con el propio punto): el punto queda como nuevo."""
    out: dict[str, tuple[str, str | None, str]] = {}
    for c in update.get("clasificacion") or []:
        key, other, relation = _ref(c.get("nuevo")), _ref(c.get("existente")), c.get("relacion", "nuevo")
        if key not in by_key or relation not in ("mismo", "dudoso") or other == key \
                or (other not in by_id and other not in by_key):
            continue
        out[key] = (relation, other, str(c.get("motivo") or "").strip())
    return out


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


def hidden_block(items: list[dict[str, Any]]) -> str:
    """Los puntos que borró el usuario, con su id, para que la IA no los vuelva a crear."""
    labels = {"tarea": "tarea", "decision": "decisión", "duda": "duda"}
    return "\n".join(f"- [{short_id(it)}] {labels[it['kind']]}: {it['text']}" for it in items if it.get("hidden"))


def analysis_text(a: dict[str, Any], points: list[dict[str, Any]], signals: list[dict[str, Any]],
                  max_chars: int = 12000) -> str:
    """Lo que la IA necesita del vídeo para actualizar el seguimiento: sus puntos, las señales verificadas y
    el resumen."""
    labels = {"tarea": "tarea", "decision": "decisión", "duda": "duda"}
    parts = []
    if points:
        parts.append("Puntos de este vídeo (se añadirán al estado salvo que digas que son el mismo que uno anterior):\n"
                     + "\n".join(f"- [{p['key']}] {labels[p['kind']]}: {p['text']}"
                                 + (f" (responsable: {p['owner']})" if p["owner"] else "")
                                 + (f" (plazo: {p['due']})" if p["due"] else "") + (f" [{p['t']}]" if p["t"] else "")
                                 for p in points))
    if signals:
        parts.append("Menciones de los asuntos anteriores en este vídeo:\n" + "\n".join(
            f"- [{x['id']}] {x['evento']}{'' if x['verified'] else ' (sin comprobar)'} en {x['t']}: «{x['cita']}»"
            for x in signals))
    if a.get("resumen_breve"):
        parts.append("Resumen breve del vídeo:\n" + a["resumen_breve"])
    if a.get("resumen_detallado"):
        parts.append("Resumen detallado del vídeo:\n" + a["resumen_detallado"][:max_chars])
    return "\n\n".join(parts)


MOMENT_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})[ T·]+(\d{1,2}:\d{2}:\d{2})\]")


def link_moments(text: str, videos: list[dict[str, Any]]) -> str:
    """Las marcas «[AAAA-MM-DD hh:mm:ss]» del resumen, con enlace al documento del vídeo de esa fecha."""
    links = {f"{v['date']:%Y-%m-%d}": v.get("link") for v in videos}

    def repl(m: re.Match[str]) -> str:
        link = links.get(m.group(1))
        label = f"{m.group(1)} {m.group(2)}"
        return f"[{label}]({link}/resumen.md)" if link else label
    return MOMENT_RE.sub(repl, text)


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
        out += ["## Resumen", "", link_moments(f["summary"].strip(), videos), ""]
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
                    if e.get("cita"):
                        note += f" («{e['cita']}»)"
                    w = where(e)
                    label = EVENT_LABELS.get(e["evento"], e["evento"])
                    if e.get("posible"):
                        state = "descartado por ti" if e.get("descartado") else "sin confirmar"
                        label += f" (posible: {EVENT_LABELS.get(e['posible'], e['posible'])}, {state})"
                    out.append(f"  - {label}{(' · ' + w) if w else ''}{note}")
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
