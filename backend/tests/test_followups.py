"""Seguimientos: estado de los puntos, contexto, aplicar y deshacer vídeos, lo manual y la API."""

from datetime import datetime

import pytest
from sqlmodel import select

from app import followups as F
from app import followups_store as FS
from app import main
from app.config import Settings
from app.models import Followup, FollowupItem, FollowupVideo, Job, Segment, Video
from app.prompts import FOLLOW_CHECK_SCHEMA

# Fechas sin zona horaria, como las de la base de datos
D1, D2, D3 = datetime(2026, 10, 4, 19), datetime(2026, 10, 5, 17), datetime(2026, 10, 6, 10)  # noqa: DTZ001
AT = datetime(2026, 10, 11)  # noqa: DTZ001


def ev(video_id, date, evento, t="00:01:00", source="ia", nota=""):
    return {"video_id": video_id, "date": date.isoformat() if date else None, "t": t, "evento": evento,
            "nota": nota, "source": source, "at": AT.isoformat()}


def item(id_, kind, text, events, manual=False, hidden=False):
    return {"id": id_, "kind": kind, "text": text, "owner": "", "due": "", "manual": manual, "hidden": hidden,
            "events": events, "status": F.derive_status(kind, events)}


# --------------------------------------------------------------------------- lógica pura

def test_status_comes_from_the_last_event():
    assert F.derive_status("tarea", [ev(1, D1, "creada")]) == "abierta"
    assert F.derive_status("tarea", [ev(1, D1, "creada"), ev(2, D2, "hecha"), ev(2, D2, "avanza")]) == "hecha"
    assert F.derive_status("tarea", [ev(1, D1, "creada"), ev(2, D2, "hecha"), ev(3, D3, "reabierta")]) == "abierta"
    assert F.derive_status("decision", [ev(1, D1, "creada"), ev(2, D2, "cambiada")]) == "cambiada"
    assert F.status_for_event("duda", "resuelta") == "resuelta" and F.status_for_event("duda", "abierta") == "reabierta"


def test_state_at_only_counts_previous_videos():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada"), ev(2, D2, "hecha")]),
             item(2, "duda", "¿Quién paga?", [ev(2, D2, "creada")]),
             item(3, "tarea", "Llamar al banco", [ev(None, None, "creada", source="manual")], manual=True),
             item(4, "tarea", "Borrada", [ev(1, D1, "creada")], manual=True, hidden=True)]
    before_2 = {it["id"]: it["status"] for it in F.state_at(items, D2)}
    assert before_2 == {1: "abierta", 3: "abierta"}  # lo del vídeo 2 aún no ha pasado; lo manual cuenta siempre
    assert {it["id"]: it["status"] for it in F.state_at(items, None)} == {1: "hecha", 2: "abierta", 3: "abierta"}


def test_context_block_with_ids_and_limit():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada")]),
             item(2, "decision", "Usar la cuenta común", [ev(1, D1, "creada")]),
             item(3, "duda", "¿Quién paga?", [ev(1, D1, "creada"), ev(2, D2, "resuelta")])]
    block = F.context_block("Tutoría", "", "Va bien.", items, [D1, D2], D3, with_ids=True)
    assert "[T1] Enviar el informe" in block and "[D2] Usar la cuenta común" in block
    assert "Cerrado recientemente" in block and "[P3]" in block and "Va bien." in block
    assert "[T1]" not in F.context_block("Tutoría", "", "", items, [D1, D2], D3)
    # Antes del primer vídeo no hay nada
    assert F.context_block("Tutoría", "", "", items, [D1, D2], D1) == ""
    many = [item(i, "tarea", f"Tarea número {i} con un texto largo", [ev(1, D1, "creada")]) for i in range(1, 200)]
    block = F.context_block("T", "", "", many, [D1], D2, max_chars=1000)
    assert len(block) < 1100 and "más)" in block


UTTS = [{"start": 290.0, "end": 300.0, "text": "Por cierto, el informe ya se lo mandé al gestor ayer."},
        {"start": 355.0, "end": 362.0, "text": "La cita con el banco ya la tengo para el jueves."}]


def sig(id_, evento, t, cita, verified=True):
    return {"id": id_, "evento": evento, "t": t, "cita": cita, "verified": verified}


def test_apply_update_validates_the_answer():
    items = [item(1, "tarea", "Enviar el informe al gestor", [ev(1, D1, "creada")]),
             item(2, "tarea", "Pedir cita", [ev(1, D1, "creada")], manual=True),
             item(3, "duda", "¿Hay que firmar ante notario?", [ev(1, D1, "creada")], hidden=True, manual=True),
             item(4, "duda", "¿Quién paga la cuota?", [ev(1, D1, "creada")])]
    cita = "el informe ya se lo mandé al gestor"
    signals = [
        sig("T1", "hecha", "00:05:00", cita),
        sig("T1", "avanza", "00:04:00", "se habla del informe"),  # ya cambia de estado en este vídeo
        sig("T9", "hecha", "00:05:00", cita),  # no existe
        sig("T1", "resuelta", "00:05:00", cita),  # no vale para una tarea
        sig("T2", "hecha", "00:06:00", "la cita con el banco ya la tengo"),  # manual: queda como avance
        sig("P4", "resuelta", "00:07:00", "lo paga la empresa", verified=False),  # sin cita: posible
    ]
    update = {"clasificacion": [
        {"nuevo": "N1", "relacion": "mismo", "existente": "T1", "motivo": "la misma tarea"},
        {"nuevo": "N4", "relacion": "mismo", "existente": "T9", "motivo": "no existe"},
        {"nuevo": "N5", "relacion": "mismo", "existente": "[P3]", "motivo": "la borró el usuario"},
        {"nuevo": "N6", "relacion": "dudoso", "existente": "P4", "motivo": "puede ser la misma cuota"},
        {"nuevo": "N7", "relacion": "mismo", "existente": "N6", "motivo": "repite la tarea como duda"},
        {"nuevo": "N6", "relacion": "nuevo", "existente": "", "motivo": "se ignora: ya está clasificado arriba"}]}
    points = [{"key": "N1", "kind": "tarea", "text": "Mandar el informe al gestor", "owner": "", "due": "", "t": "00:05:00"},
              {"key": "N2", "kind": "duda", "text": "¿Hace falta el aval?", "owner": "", "due": "", "t": "00:08:00"},
              {"key": "N3", "kind": "duda", "text": "¿Hay que firmar ante notario?", "owner": "", "due": "", "t": "00:09:00"},
              {"key": "N4", "kind": "tarea", "text": "Llamar al banco", "owner": "Ana", "due": "", "t": "sin hora"},
              {"key": "N5", "kind": "duda", "text": "¿Firmamos con el notario?", "owner": "", "due": "", "t": "00:10:00"},
              {"key": "N6", "kind": "tarea", "text": "Pagar la cuota del seguro", "owner": "", "due": "", "t": "00:11:00"},
              {"key": "N7", "kind": "duda", "text": "¿Cuándo se paga la cuota del seguro?", "owner": "", "due": "",
               "t": "00:12:00"}]
    plan = F.apply_update(items, update, 2, D2, 25 * 60, AT, points, signals)
    evs = [(iid, e["evento"], e.get("posible")) for iid, e in plan["events"]]
    # Un cambio sin una frase que lo diga queda como posible (no cambia el estado: lo confirma el usuario)
    assert evs == [(1, "hecha", None), (2, "avanza", None), (4, "avanza", "resuelta")]
    first = plan["events"][0][1]
    assert first["date"] == D2.isoformat() and first["t"] == "00:05:00" and first["cita"] == cita
    # Lo decidió el usuario: el vídeo solo se anota como avance
    assert "hecha" in plan["events"][1][1]["nota"]
    assert len(plan["discarded"]) == 6
    # N1 es la misma tarea; N3 casi repite el texto de una borrada por el usuario y N5 la IA la da por esa
    # borrada; N4 se relaciona con un punto que no existe: se añade, sin momento; N7 repite N6 en el mismo vídeo
    assert [(n["text"], n["events"][0]["t"]) for n in plan["new"]] == [
        ("¿Hace falta el aval?", "00:08:00"), ("Llamar al banco", ""), ("Pagar la cuota del seguro", "00:11:00")]
    # Dudoso: se crea, pero con la duda para que la decida el usuario
    assert plan["new"][2]["review"] == {"tipo": "duplicado", "de": 4, "texto": "¿Quién paga la cuota?",
                                        "motivo": "puede ser la misma cuota"}
    assert plan["new"][0]["review"] == {}


def test_quotes_and_signals():
    assert F.quoted("el informe ya se lo mandé al gestor", UTTS, 300)
    assert not F.quoted("el informe ya se lo mandé al gestor", UTTS, 600)  # dicho, pero no en ese momento
    assert not F.quoted("sí, vale", UTTS, 300)  # demasiado corta para demostrar nada
    # La IA a veces junta trozos con puntos suspensivos y comillas: vale si cada trozo se dice ahí
    assert F.quoted('"Por cierto, el informe... se lo mandé al gestor ayer."', UTTS, 300)
    assert not F.quoted('"Por cierto, el informe... lo firmó el notario"', UTTS, 300)
    raw = [{"id": "[t1]", "evento": "hecha", "t": "00:04:55", "cita": "«el informe ya se lo mandé al gestor»"},
           {"id": "T1", "evento": "hecha", "t": "00:04:56", "cita": "repetida"},
           {"id": "T2", "evento": "hecha", "t": "00:06:00", "cita": "esto no lo dice nadie en la reunión"},
           {"id": "T3", "evento": "avanza", "t": "00:06:00", "cita": "esto tampoco lo dice nadie"},
           {"id": "T4", "evento": "hecha", "t": "02:00:00", "cita": "fuera del vídeo"},
           {"id": "X5", "evento": "hecha", "t": "00:01:00", "cita": "id mal formado"}]
    assert F.check_signals(raw, UTTS, 1500) == [
        {"id": "T1", "evento": "hecha", "t": "00:04:55", "cita": "el informe ya se lo mandé al gestor", "verified": True},
        {"id": "T2", "evento": "hecha", "t": "00:06:00", "cita": "esto no lo dice nadie en la reunión", "verified": False}]


def test_internal_ids_out_of_the_summary():
    assert F.strip_ids("La duda (P19) sigue abierta y la tarea [T3] está hecha.") ==         "La duda sigue abierta y la tarea está hecha."


def test_points_from_the_analysis():
    a = {"tareas": [{"responsable": "Ana", "tarea": "Enviar el informe", "plazo": "Sin especificar", "t": "00:01:00"},
                    {"responsable": "", "tarea": " ", "plazo": "", "t": ""}],
         "decisiones": [{"decision": "Abrir la cuenta", "t": "00:02:00"}],
         "pendientes": ["Texto de un análisis antiguo", {"pendiente": "¿Quién paga?", "t": "00:03:00"}]}
    pts = F.analysis_points(a)
    assert [(p["key"], p["kind"], p["text"], p["due"], p["t"]) for p in pts] == [
        ("N1", "tarea", "Enviar el informe", "", "00:01:00"), ("N2", "decision", "Abrir la cuenta", "", "00:02:00"),
        ("N3", "duda", "Texto de un análisis antiguo", "", ""), ("N4", "duda", "¿Quién paga?", "", "00:03:00")]


def test_owner_with_the_names_of_known_people():
    people = [{"id": 1, "name": "Iosu Urcelay", "aliases": []},
              {"id": 2, "name": "José Luis Pérez", "aliases": ["Selu"]},
              {"id": 3, "name": "Ana García", "aliases": []}]
    assert F.normalize_owner("Grupo Barymont (Iosu/Selu)", people) == "Iosu Urcelay, José Luis Pérez"
    assert F.normalize_owner("Iosu y Selu", people) == "Iosu Urcelay, José Luis Pérez"
    assert F.normalize_owner("ana garcia", people) == "Ana García"
    assert F.normalize_owner("Ana y el proveedor", people) == "Ana García, el proveedor"
    assert F.normalize_owner("Selu, José Luis", people) == "José Luis Pérez"
    # Si no hay ninguna persona conocida, se queda tal cual
    assert F.normalize_owner("Gestoría (externa)", people) == "Gestoría (externa)"
    assert F.normalize_owner("El equipo", people) == "El equipo"
    assert F.normalize_owner("", people) == ""
    assert F.normalize_owner("Iosu", []) == "Iosu"


def test_events_in_order_and_no_advance_in_the_creating_video():
    manual = ev(None, None, "hecha", source="manual")
    events = [ev(1, D1, "creada"), manual, ev(2, D2, "avanza", t="00:05:00"), ev(2, D2, "avanza", t="00:01:00")]
    assert [(e["source"], e["t"]) for e in F.sort_events(events)] == [
        ("ia", "00:01:00"), ("ia", "00:01:00"), ("ia", "00:05:00"), ("manual", "00:01:00")]
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada")])]
    plan = F.apply_update(items, {}, 1, D1, 600, AT, [], [sig("T1", "avanza", "00:02:00", "se repite")])
    assert plan["events"] == []
    # Tampoco cuando el punto es manual y el vídeo que lo creó dice que cambia (al rehacer el estado)
    manual_items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada")], manual=True)]
    plan = F.apply_update(manual_items, {}, 1, D1, 600, AT, [], [sig("T1", "hecha", "00:02:00", "ya está hecho")])
    assert plan["events"] == []
    # Como al rehacer: el estado anterior a la fecha del vídeo ya no tiene su hito de creación
    edited = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada"), ev(None, None, "hecha", source="manual")],
                   manual=True)]
    before = F.state_at(edited, D1)
    assert [e["source"] for e in before[0]["events"]] == ["manual"] and before[0]["created_video"] == 1
    plan = F.apply_update(before, {}, 1, D1, 600, AT, [], [sig("T1", "avanza", "00:02:00", "se habla de ello")])
    assert plan["events"] == []


def test_revert_keeps_what_the_user_did():
    items = [item(1, "tarea", "A", [ev(1, D1, "creada"), ev(2, D2, "hecha")]),
             item(2, "tarea", "B", [ev(2, D2, "creada")]),
             item(3, "tarea", "C", [ev(2, D2, "creada")], manual=True),  # la IA lo creó y el usuario lo editó
             item(4, "tarea", "D", [ev(None, None, "creada", source="manual"), ev(2, D2, "avanza")], manual=True)]
    plan = F.revert(items, {2})
    assert plan["delete"] == [2]
    assert [e["evento"] for e in plan["update"][1]] == ["creada"]
    assert [e["evento"] for e in plan["update"][3]] == ["creada"]
    assert [e["source"] for e in plan["update"][4]] == ["manual"]


def test_render_markdown():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada", t="00:02:00"), ev(2, D2, "hecha")])]
    videos = [{"id": 1, "title": "Primera", "date": D1, "link": "../2026-10-04%20-%20Primera", "contribution": "Empieza",
               "applied": True},
              {"id": 2, "title": "Segunda", "date": D2, "link": "", "contribution": "", "applied": False}]
    summary = "Empieza el 4 [2026-10-04 00:01:30] y sigue [2026-10-05 00:03:00]; sin vídeo [2026-10-09 00:01:00]."
    md = F.render_markdown({"name": "Tutoría", "summary": summary}, items, videos)
    assert "# Seguimiento: Tutoría" in md and "**[hecha]** Enviar el informe" in md
    assert "[2026-10-04 00:02:00](../2026-10-04%20-%20Primera/resumen.md)" in md and "*(sin aplicar)*" in md
    # Las marcas con fecha del resumen enlazan al vídeo de ese día (si tiene carpeta)
    assert ("Empieza el 4 [2026-10-04 00:01:30](../2026-10-04%20-%20Primera/resumen.md) y sigue 2026-10-05 00:03:00;"
            " sin vídeo 2026-10-09 00:01:00.") in md


# --------------------------------------------------------------------------- con la base de datos

@pytest.fixture(autouse=True)
def tmp_analyzed(tmp_path, monkeypatch):
    monkeypatch.setattr(FS, "load_settings", lambda: Settings(analyzed_dir=str(tmp_path / "Analizados")))
    return tmp_path / "Analizados"


def _video(session, date, title, analysis=None, utts=()):
    v = Video(source_path=f"{title}.mkv", title=title, status="done", recorded_at=date, duration=25 * 60,
              analysis=analysis or ANALYSES.get(title) or {"resumen_breve": title})
    session.add(v)
    session.commit()
    for i, u in enumerate(utts or UTTS_BY_TITLE.get(title, [])):
        session.add(Segment(video_id=v.id, idx=i, start=u["start"], end=u["end"], text=u["text"]))
    session.add(Job(video_id=v.id, status="done"))
    session.commit()
    return v


class FakeAsk:
    """IA de mentira: responde por título del vídeo y guarda lo que recibe."""

    def __init__(self, answers, mentions=None):
        self.answers, self.mentions, self.calls = answers, mentions or {}, []

    def __call__(self, system, user, schema, thinking=False):
        if schema is FOLLOW_CHECK_SCHEMA:
            assert thinking  # se busca con el modo razonamiento
            date = next(d for d in self.mentions if d in user) if any(d in user for d in self.mentions) else None
            return {"menciones": self.mentions.get(date, [])}
        self.calls.append(user)
        title = next(t for t in self.answers if t in user)
        return self.answers[title]


ANALYSES = {
    "Primera": {"resumen_breve": "Primera", "tareas": [
        {"responsable": "Iosu", "tarea": "Enviar el informe", "plazo": "Sin especificar", "t": "00:02:00"}],
        "decisiones": [], "pendientes": [{"pendiente": "¿Quién paga la cuota?", "t": "00:03:00"}]},
    "Segunda": {"resumen_breve": "Segunda", "tareas": [
        {"responsable": "Iosu", "tarea": "Enviar el informe al gestor", "plazo": "", "t": "00:01:00"}],
        "decisiones": [{"decision": "Abrir la cuenta común", "t": "00:04:00"}], "pendientes": []},
}
UTTS_BY_TITLE = {"Segunda": [{"start": 55.0, "end": 64.0, "speaker": "S1",
                              "text": "El informe ya lo he enviado esta mañana, está hecho."}]}
ANSWERS = {
    "Primera": {"clasificacion": [], "resumen": "Empieza el tema.", "aporte": "Se plantea."},
    "Segunda": {"clasificacion": [{"nuevo": "N1", "relacion": "mismo", "existente": "T1", "motivo": "el mismo informe"}],
                "resumen": "Informe enviado y cuenta decidida.", "aporte": "Se cierra el informe."},
}
MENTIONS = {"2026-10-05": [{"id": "T1", "evento": "hecha", "t": "00:01:00",
                            "cita": "el informe ya lo he enviado esta mañana"}]}


def _followup(session, *videos):
    f = Followup(name="Tutoría")
    session.add(f)
    session.commit()
    for v in videos:
        session.add(FollowupVideo(followup_id=f.id, video_id=v.id))
    session.commit()
    return f


def test_mentions_retry_truncated_block_in_halves(session):
    """Si el razonamiento agota el límite de tokens, el bloque se repite partido en dos mitades."""
    from app.llm import LLMTruncated

    utts = [{"start": 60.0 * i, "end": 60.0 * i + 50, "speaker": "S1", "text": f"Frase número {i} de la reunión"}
            for i in range(6)]
    v = _video(session, D2, "Segunda", utts=utts)
    state = [item(1, "tarea", "Enviar el informe", [ev(99, D1, "creada")])]
    bodies = []

    def ask(system, user, schema, thinking=False):
        bodies.append(user)
        if len(bodies) == 1:
            raise LLMTruncated("se cortó")
        return {"menciones": [{"id": "T1", "evento": "hecha", "t": "00:05:00", "cita": "Frase número 5 de la reunión"}]
                if "Frase número 5" in user else []}

    out = FS.mentions(session, v, state, FS.video_utts(session, v.id), ask, D2)
    assert len(bodies) == 3 and "Frase número 0" in bodies[1] and "Frase número 5" in bodies[2]
    assert "Frase número 5" not in bodies[1]
    assert [(x["id"], x["evento"], x["verified"]) for x in out] == [("T1", "hecha", True)]

    def always(system, user, schema, thinking=False):
        raise LLMTruncated("se cortó")

    with pytest.raises(LLMTruncated):
        FS.mentions(session, v, state, FS.video_utts(session, v.id), always, D2)


def test_apply_in_order_and_rebuild_respects_manual(session, tmp_analyzed):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = _followup(session, v1, v2)
    ask = FakeAsk(ANSWERS, MENTIONS)
    # Solo cuenta para medir el tiempo el vídeo en que se buscan menciones (el primero no tiene estado anterior)
    assert FS.rebuild_from(session, f, None, ask) == 25
    assert FS.rebuild_seconds(session, f, None) == FS.rebuild_seconds(session, f, D2) == 25 * 6.0
    its = {it["text"]: it for it in FS.items(session, f.id)}
    assert its["Enviar el informe"]["status"] == "hecha" and its["Abrir la cuenta común"]["status"] == "vigente"
    assert f.summary == "Informe enviado y cuenta decidida."
    # El segundo vídeo recibe el estado del primero, con sus ids, y las menciones comprobadas
    assert "[T" in ask.calls[1] and "Empieza el tema." in ask.calls[1] and "«el informe ya lo he enviado" in ask.calls[1]
    assert (tmp_analyzed / "Seguimiento - Tutoría" / "seguimiento.md").exists()

    # El usuario reabre la tarea y edita el resumen; al rehacer, la IA no lo deshace
    task = session.get(FollowupItem, its["Enviar el informe"]["id"])
    task.events = [*task.events, ev(None, None, "reabierta", source="manual")]
    task.manual, task.status = True, "abierta"
    f.summary, f.summary_manual = "Mi resumen", True
    session.add(task), session.add(f)
    session.commit()
    FS.rebuild_from(session, f, D2, ask)
    its = {it["text"]: it for it in FS.items(session, f.id)}
    assert its["Enviar el informe"]["status"] == "abierta"  # el «hecha» del vídeo queda como avance
    # El hito del vídeo va en su fecha; el cambio manual, más reciente, queda el último y manda
    assert [e["evento"] for e in its["Enviar el informe"]["events"]] == ["creada", "avanza", "reabierta"]
    assert f.summary == "Mi resumen" and f.summary_ai == "Informe enviado y cuenta decidida."
    assert len([it for it in its.values() if it["text"] == "Abrir la cuenta común"]) == 1


def test_rebuild_tells_the_ai_the_series_and_what_the_user_deleted(session, tmp_analyzed):
    """Al rehacer, la IA recibe lo que aportó cada vídeo anterior, los puntos borrados y de qué trata el vídeo."""
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = _followup(session, v1, v2)
    checks = []

    class Ask(FakeAsk):
        def __call__(self, system, user, schema, thinking=False):
            if schema is FOLLOW_CHECK_SCHEMA:
                checks.append(user)
            return super().__call__(system, user, schema, thinking)

    FS.rebuild_from(session, f, None, Ask(ANSWERS, MENTIONS))
    task = next(it for it in session.exec(select(FollowupItem)) if it.text == "Enviar el informe")
    task.hidden, task.manual = True, True
    session.add(task)
    session.commit()
    ask = Ask(ANSWERS, MENTIONS)
    FS.rebuild_from(session, f, D2, ask)
    assert "Lo que aportó cada vídeo anterior, en orden:\n- 2026-10-04: Se plantea." in ask.calls[-1]
    assert "Puntos que el usuario borró" in ask.calls[-1] and f"[T{task.id}] tarea: Enviar el informe" in ask.calls[-1]
    assert "De qué trata esta reunión: «Segunda». Segunda" in checks[-1]


def test_update_for_video_older_video_marks_stale(session):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = _followup(session, v2)
    FS.update_for_video(session, v2, v2.analysis, set(), FakeAsk(ANSWERS))
    assert session.get(FollowupVideo, (f.id, v2.id)).applied and f.stale_from is None
    # Un vídeo anterior que llega después: no se puede aplicar en orden sin rehacer
    session.add(FollowupVideo(followup_id=f.id, video_id=v1.id))
    session.commit()
    FS.update_for_video(session, v1, v1.analysis, set(), FakeAsk(ANSWERS))
    assert f.stale_from == D1 and "anterior" in f.stale_reason
    # Regenerar un vídeo ya aplicado sin rehacer también lo deja desactualizado
    f.stale_from = None
    FS.update_for_video(session, v2, v2.analysis, set(), FakeAsk(ANSWERS))
    assert f.stale_from == D2


def test_restore_version(session):
    v1 = _video(session, D1, "Primera")
    f = _followup(session, v1)
    FS.rebuild_from(session, f, None, FakeAsk(ANSWERS))
    version = FS.record_version(session, f, "Prueba")
    FS.revert_videos(session, f, {v1.id})
    assert FS.items(session, f.id) == [] and f.summary == ""
    FS.restore(session, f, version)
    assert len(FS.items(session, f.id)) == 2 and f.summary == "Empieza el tema." and f.stale_from is None


# --------------------------------------------------------------------------- API

def test_api_crud_items_and_versions(client, session):
    f = client.post("/api/followups", json={"name": " Tutoría "}).json()
    assert f["name"] == "Tutoría" and f["items"] == [] and f["n_videos"] == 0
    assert client.post(f"/api/followups/{f['id']}/items", json={"kind": "tarea", "text": ""}).status_code == 400
    f = client.post(f"/api/followups/{f['id']}/items", json={"kind": "tarea", "text": "Pedir cita"}).json()
    [it] = f["items"]
    assert it["manual"] and it["status"] == "abierta"
    f = client.put(f"/api/followups/{f['id']}/items/{it['id']}", json={"status": "hecha"}).json()
    assert f["items"][0]["status"] == "hecha" and f["items"][0]["events"][-1]["source"] == "manual"
    assert client.put(f"/api/followups/{f['id']}/items/{it['id']}", json={"status": "vigente"}).status_code == 400
    f = client.put(f"/api/followups/{f['id']}", json={"summary": "Mío"}).json()
    assert f["summary"] == "Mío" and f["summary_manual"]
    f = client.delete(f"/api/followups/{f['id']}/items/{it['id']}").json()
    assert f["items"] == []  # oculto, no borrado
    assert session.get(FollowupItem, it["id"]).hidden
    versions = client.get(f"/api/followups/{f['id']}/versions").json()
    with_item = next(v for v in versions if v["items"] == 1)
    f = client.post(f"/api/followups/{f['id']}/versions/{with_item['id']}/restore").json()
    assert len(f["items"]) == 1
    f = client.put(f"/api/followups/{f['id']}", json={"status": "archivado"}).json()
    assert f["status"] == "archivado"
    assert client.delete(f"/api/followups/{f['id']}").json() == {"ok": True}
    assert client.get(f"/api/followups/{f['id']}").status_code == 404


def test_api_videos(client, session, tmp_path):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = client.post("/api/followups", json={"name": "Tutoría"}).json()
    # Añadir y aplicar: encola un trabajo que solo rehace el seguimiento
    r = client.post(f"/api/followups/{f['id']}/videos/{v1.id}", json={"apply": True}).json()
    job = session.get(Job, r["job_id"])
    session.refresh(job)
    assert job.status == "queued" and job.options["only"] == ["follow"] and job.options["follow_rebuild"] == [f["id"]]
    assert r["busy"]
    assert client.post(f"/api/followups/{f['id']}/videos/{v1.id}").status_code == 409
    # Sin aplicar: queda desactualizado
    r = client.post(f"/api/followups/{f['id']}/videos/{v2.id}", json={"apply": False}).json()
    assert r["stale_from"] and r["n_videos"] == 2
    detail = client.get(f"/api/videos/{v2.id}").json()
    assert detail["followups"] == [{"id": f["id"], "name": "Tutoría", "status": "abierto", "applied": False}]
    # Quitar sin rehacer un vídeo que no estaba aplicado: no cambia nada más
    r = client.delete(f"/api/followups/{f['id']}/videos/{v2.id}").json()
    assert r["n_videos"] == 1

    # Encolar un vídeo nuevo dentro del seguimiento
    video = tmp_path / "nuevo.mkv"
    video.write_bytes(b"x")
    r = client.post("/api/jobs", json={"path": str(video), "followup_ids": [f["id"]]}).json()
    assert session.get(FollowupVideo, (f["id"], r["video_id"]))
    client.put(f"/api/followups/{f['id']}", json={"status": "archivado"})
    video2 = tmp_path / "otro.mkv"
    video2.write_bytes(b"x")
    assert client.post("/api/jobs", json={"path": str(video2), "followup_ids": [f["id"]]}).status_code == 400


def test_api_video_document_lists_followups(client, session, tmp_analyzed):
    """Al añadir o quitar un vídeo ya publicado, su `resumen.md` dice en qué seguimientos está."""
    v = _video(session, D1, "Primera")
    v.folder = str(tmp_analyzed / "2026-10-04 - Primera")
    (tmp_analyzed / "2026-10-04 - Primera").mkdir(parents=True)
    session.add(v)
    session.commit()
    doc = tmp_analyzed / "2026-10-04 - Primera" / "resumen.md"
    f = client.post("/api/followups", json={"name": "Tutoría"}).json()
    client.post(f"/api/followups/{f['id']}/videos/{v.id}", json={"apply": False})
    assert "**Seguimientos:** [Tutoría](../Seguimiento%20-%20Tutoría/seguimiento.md)" in doc.read_text(encoding="utf-8")
    client.delete(f"/api/followups/{f['id']}/videos/{v.id}")
    assert "Seguimientos" not in doc.read_text(encoding="utf-8")


def test_regenerate_passes_follow_rebuild_once(client, session, tmp_path, monkeypatch):
    v = _video(session, D1, "Primera")
    f = _followup(session, v)
    monkeypatch.setattr(main.regen, "availability", lambda *_: dict.fromkeys(main.regen.LEVELS, ""))
    info = client.get(f"/api/videos/{v.id}/regenerate").json()
    assert info["followups"][0]["id"] == f.id
    r = client.post(f"/api/videos/{v.id}/regenerate", json={"level": "analysis", "follow_rebuild": [f.id]}).json()
    job = session.get(Job, r["job_id"])
    session.refresh(job)
    assert job.options["follow_rebuild"] == [f.id] and "follow" in job.options["redo"]
    job.status = "done"
    session.add(job)
    session.commit()
    client.post(f"/api/videos/{v.id}/learn")
    session.refresh(job)
    assert "follow_rebuild" not in job.options  # no se arrastra al siguiente encolado


def test_video_documents_link_their_followups():
    from app.pipeline.export import summary_md

    meta = {"title": "T", "date": "2026-10-05", "duration": "0:25:00",
            "followups": [("Tutoría", "../Seguimiento%20-%20Tutoría/seguimiento.md"), ("Sin carpeta", "")]}
    md = summary_md(meta, {})
    assert "- **Seguimientos:** [Tutoría](../Seguimiento%20-%20Tutoría/seguimiento.md), Sin carpeta" in md


def test_same_task_for_several_people_keeps_all_owners():
    """La misma tarea encargada a dos personas en el mismo vídeo queda como un punto con las dos."""
    points = [{"key": "N1", "kind": "tarea", "text": "Recopilar las facturas y las pólizas", "owner": "Edgar", "due": "",
               "t": "00:01:00"},
              {"key": "N2", "kind": "tarea", "text": "Recopilar las facturas y las pólizas", "owner": "Sandra", "due": "",
               "t": "00:01:00"},
              {"key": "N3", "kind": "tarea", "text": "Firmar la protección de datos", "owner": "Edgar", "due": "",
               "t": "00:02:00"},
              {"key": "N4", "kind": "tarea", "text": "Aceptar el documento de protección de datos", "owner": "Sandra",
               "due": "", "t": "00:03:00"}]
    update = {"clasificacion": [{"nuevo": "N4", "relacion": "mismo", "existente": "N3", "motivo": "la misma firma"}]}
    plan = F.apply_update([], update, 1, D1, 25 * 60, AT, points, [])
    assert [(n["text"], n["owner"]) for n in plan["new"]] == [
        ("Recopilar las facturas y las pólizas", "Edgar, Sandra"), ("Firmar la protección de datos", "Edgar, Sandra")]
