"""Cola de trabajos: un único hilo procesa los vídeos uno a uno (la GPU es un recurso exclusivo).

Cada fase deja una marca `<fase>.done` en la carpeta de trabajo; si la app se cierra a mitad,
al reiniciar el trabajo se reanuda desde la última fase completada.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from . import followups_store as FS
from . import knowledge_store as KS
from . import estimates, logs, removal, review, services, speaker_fix
from . import regenerate as regen
from .config import DATA_DIR, WORK_DIR, load_settings
from .db import engine
from .llm import LLMServer
from .models import Job, Keyframe, Person, Segment, Video, VoiceEmbedding, VoiceSample
from .pipeline import analyze, asr, correct, diarize, frames, identify, ingest, learn, names, vision, voiceprints, voices
from .pipeline.base import Cancelled, JobContext, free_gpu
from .pipeline.export import safe_name, unique_dir

log = logging.getLogger(__name__)

# (clave, descripción, peso en la barra de progreso global)
STAGES = [
    ("ingest", "Preparando audio", 0.02),
    ("frames", "Seleccionando fotogramas", 0.04),
    ("vision", "Analizando la pantalla", 0.16),
    ("asr", "Transcribiendo", 0.23),
    ("align", "Alineando palabras", 0.06),
    ("diarize", "Separando hablantes", 0.10),
    ("voices", "Comprobando las voces", 0.02),
    ("names", "Unificando nombres", 0.01),
    ("identify", "Identificando personas", 0.01),
    ("correct", "Corrigiendo términos", 0.04),
    ("analyze", "Resumiendo", 0.19),
    ("voiceprints", "Guardando las voces", 0.01),
    ("follow", "Actualizando seguimientos", 0.02),
    ("learn", "Aprendiendo del vídeo", 0.09),
    ("publish", "Publicando resultados", 0.02),
]
GPU_TORCH_STAGES = {"asr", "align", "diarize", "voices", "voiceprints"}
# Solo al aplicar la revisión del vídeo (o en trabajos de una sola fase): sin revisar, el vídeo no cuenta
AFTER_REVIEW = {"voiceprints", "follow", "learn"}
# Ficheros de reanudación que se borran al repetir una fase
PARTIALS = {
    "vision": ("vision.partial.json",),
    "analyze": ("analysis.partial.json",),
    "learn": ("learn.partial.json", "learn_error.json", "screen_judgment.raw.json", "judgment.raw.json",
              "judgment_error.json"),
}
STAGE_LABELS = {k: d for k, d, _ in STAGES}


FINISH_LABELS = {"done": "terminado", "error": "con error", "cancelled": "cancelado"}

# Fases cuyo mensaje final lleva contenido del vídeo (el título): en el registro van sus recuentos
QUIET_SUMMARY = {"analyze"}


def job_kind(options: dict[str, Any]) -> str:
    """Qué hace un trabajo, para el registro: análisis, aplicar la revisión, regenerar o fases sueltas."""
    if options.get("apply"):
        what = "aplicar la revisión"
    elif options.get("only"):
        what = "solo " + ", ".join(options["only"])
    elif options.get("redo"):
        what = "repetir " + ", ".join(options["redo"])
    else:
        what = "análisis"
    if options.get("follow_rebuild"):
        what += f"; rehacer los seguimientos {', '.join(map(str, options['follow_rebuild']))}"
    return what


def is_short(job: Job | dict) -> bool:
    """Trabajo corto: aplicar la revisión de un vídeo o una sola fase (rehacer un seguimiento, aprender…)."""
    options = job if isinstance(job, dict) else (job.options or {})
    return bool(options.get("apply") or options.get("only"))


def work_dir(job_id: int) -> Path:
    return WORK_DIR / f"job_{job_id}"


class Worker:
    def __init__(self) -> None:
        self._wake = threading.Event()
        self._cancel: dict[int, threading.Event] = {}
        self._thread = threading.Thread(target=self._loop, name="worker", daemon=True)
        self.current: int | None = None

    def start(self) -> None:
        with Session(engine) as s:
            for job in s.exec(select(Job).where(Job.status == "running")):
                job.status, job.message = "queued", "Reanudando tras reinicio"
                s.add(job)
            s.commit()
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def cancel(self, job_id: int) -> None:
        ev = self._cancel.get(job_id)
        if ev:
            ev.set()

    def _loop(self) -> None:
        while True:
            with Session(engine) as s:
                review.release_waiting(s)
                queued = s.exec(select(Job).where(Job.status == "queued").order_by(Job.id)).all()
                # Los cortos primero: no tiene sentido esperar a que termine el análisis de otro vídeo
                job = min(queued, key=lambda j: (not is_short(j), j.id), default=None)
                job_id, video_id = (job.id, job.video_id) if job else (None, None)
            if job_id is None:
                self._wake.wait(5)
                self._wake.clear()
                continue
            with logs.context(job=job_id, video=video_id):
                try:
                    self._run(job_id)
                except Exception:
                    log.exception("Error inesperado en el worker")

    # ------------------------------------------------------------------
    def _run(self, job_id: int) -> None:
        settings = load_settings()
        cancel_ev = self._cancel.setdefault(job_id, threading.Event())
        self.current = job_id
        wd = work_dir(job_id)
        wd.mkdir(parents=True, exist_ok=True)

        with Session(engine) as s:
            job = s.get(Job, job_id)
            video = s.get(Video, job.video_id)
            job.status, job.started_at, job.error = "running", job.started_at or datetime.now(), ""
            video.status = "processing"
            s.add(job), s.add(video)
            s.commit()
            options = dict(job.options or {})
            kind = job_kind(options)  # antes de quitar «redo», que dice qué se regenera
            # Fases a repetir (p. ej. regenerar solo el análisis)
            for stage in options.pop("redo", []):
                (wd / f"{stage}.done").unlink(missing_ok=True)
                for f in PARTIALS.get(stage, ()):
                    (wd / f).unlink(missing_ok=True)
            job.options = options
            s.add(job)
            s.commit()
            source = regen.video_file(video) or Path(video.video_path or video.source_path)
            ctx_data = dict(
                profile=services.profile_dict(s, video.profile_id),
                people=services.people_for(s, video.profile_id),
                voice=services.voice_db(s),
                video_id=video.id,
                corrections=services.video_corrections(s, video.id),
                followups=FS.context_for_video(s, video.id),
            )

        weights_before = {}
        acc = 0.0
        for key, _, w in STAGES:
            weights_before[key] = acc
            acc += w
        state = {"stage": "", "last": 0.0}

        def report(frac: float, msg: str) -> None:
            now = time.time()
            if now - state["last"] < 0.7 and frac < 1.0:
                return
            state["last"] = now
            safe = logs.without_names(msg)
            if frac >= 1.0 and state["stage"] not in QUIET_SUMMARY and not msg.endswith(": hecho"):
                log.info("%s", safe)
            else:
                log.debug("%s (%.0f %%)", safe, frac * 100)
            w = dict((k, w) for k, _, w in STAGES)[state["stage"]]
            with Session(engine) as s:
                j = s.get(Job, job_id)
                j.stage, j.message = state["stage"], msg
                j.progress = round(weights_before[state["stage"]] + w * max(0.0, min(1.0, frac)), 4)
                s.add(j)
                s.commit()

        ctx = JobContext(
            job_id=job_id, video_id=ctx_data["video_id"], source_path=source, work_dir=wd, settings=settings,
            options=options, profile=ctx_data["profile"], people=ctx_data["people"], report=report,
            corrections=ctx_data["corrections"], followups=ctx_data["followups"],
            cancel_event=cancel_ev,
        )
        llm = LLMServer(settings)
        log.info("Empieza: %s", kind)
        only = set(options.get("only") or [])  # trabajos de una sola fase (p. ej. rehacer un seguimiento)
        apply = bool(options.get("apply"))  # aplicar la revisión del vídeo
        gated = bool(only)
        try:
            for key, label, _ in STAGES:
                marker = wd / f"{key}.done"
                state["stage"] = key
                if only and key not in only:
                    continue
                if key in AFTER_REVIEW and not apply and key not in only:
                    log.debug("«%s» se salta: se hace al aplicar la revisión", key)
                    continue
                if key == "vision" and options.get("skip_vision"):
                    ctx.save("vision.json", []), ctx.save("screen_terms.json", [])
                    marker.touch()
                if marker.exists():
                    log.debug("«%s» ya estaba hecha", key)
                    if key == "identify":
                        self._load_names(ctx)
                    continue
                if not is_short(options) and self._yield_to_short(job_id):
                    return
                if not gated and key in review.GATED_STAGES:
                    gated = True
                    if self._wait(job_id):
                        return
                ctx.check_cancel()
                with logs.context(stage=key):
                    log.info("Fase «%s»", label)
                    report(0.0, label)
                    if key in GPU_TORCH_STAGES:
                        llm.stop()  # liberar VRAM antes de cargar Whisper / pyannote
                    t0 = time.monotonic()
                    minutes = self._run_stage(key, ctx, llm, ctx_data["voice"])
                    if key not in GPU_TORCH_STAGES:
                        free_gpu()
                    marker.touch()
                    if key != "follow" or minutes:  # sin seguimientos no hay nada que medir
                        self._record_time(ctx, key, time.monotonic() - t0, minutes)
                    log.info("Fase «%s» terminada en %.1f s", label, time.monotonic() - t0)
                    report(1.0, label + ": hecho")
            self._finish(job_id, "done", "Completado")
            with Session(engine) as s:
                v = s.get(Video, ctx.video_id)
                if apply:
                    v.review = review.PROPOSALS
                elif not only:
                    v.review = review.PENDING  # análisis nuevo o regenerado: hay que revisarlo
                log.info("Revisión del vídeo: %s", v.review)
                s.add(v)
                s.commit()
                review.check_done(s, v)
                self._cleanup(wd, keep_audio=v.review != review.DONE)
        except Cancelled:
            self._finish(job_id, "cancelled", "Cancelado por el usuario")
        except Exception as e:
            log.exception("Fallo en el trabajo %s, fase «%s»", job_id, state["stage"])
            self._finish(job_id, "error", f"Error en «{STAGE_LABELS.get(state['stage'], state['stage'])}»",
                         f"{e}\n\n{traceback.format_exc()}")
        finally:
            llm.stop()
            free_gpu()
            self.current = None
            self._cancel.pop(job_id, None)

    @staticmethod
    def _yield_to_short(job_id: int) -> bool:
        """Un análisis largo cede el turno entre fase y fase si hay en cola un trabajo corto (aplicar la
        revisión de un vídeo, rehacer un seguimiento): se reanuda después desde la fase siguiente."""
        with Session(engine) as s:
            short = next((j for j in s.exec(select(Job).where(Job.status == "queued")) if is_short(j)), None)
            if short is None:
                return False
            job = s.get(Job, job_id)
            other = s.get(Video, short.video_id)
            log.info("Cede el turno al trabajo %s (vídeo %s), que es corto", short.id, short.video_id)
            job.status, job.message = "queued", f"En pausa: antes va «{other.title}»"
            s.add(job)
            s.commit()
            return True

    @staticmethod
    def _wait(job_id: int) -> bool:
        """Si un vídeo relacionado encolado antes está sin revisar, el trabajo espera (lo pesado ya está hecho)."""
        with Session(engine) as s:
            job = s.get(Job, job_id)
            other = review.blocker(s, s.get(Video, job.video_id))
            if other is None:
                return False
            log.info("Espera a que se revise el vídeo %s", other.id)
            job.status, job.message = "waiting", f"Espera a que revises «{other.title}»"
            job.options = {**(job.options or {}), "waiting_for": other.id}
            s.add(job)
            s.commit()
            return True

    @staticmethod
    def _apply_overrides(ctx: JobContext) -> None:
        """Reconstruye las intervenciones con los arreglos manuales de hablantes, que mandan sobre todo."""
        with Session(engine) as s:
            overrides = speaker_fix.overrides(s, ctx.video_id)
            labels = speaker_fix.labels_for(s, ctx.video_id, overrides)
        ctx.overrides = overrides
        voices.rebuild(ctx, overrides, labels)

    @staticmethod
    def _record_time(ctx: JobContext, stage: str, seconds: float, minutes: float | None = None) -> None:
        """Guarda cuánto ha tardado la fase, para estimar las siguientes. Nunca interrumpe el trabajo.

        `minutes`: los minutos de vídeo que ha procesado la fase, si no son los de este vídeo (al rehacer un
        seguimiento se aplican varios)."""
        try:
            duration = minutes * 60 if minutes else (ctx.load("probe.json") or {}).get("duration", 0.0)
            with Session(engine) as s:
                estimates.record(s, ctx.job_id, ctx.video_id, stage, seconds, duration,
                                 len(ctx.load("frames.json", [])))
        except Exception:
            log.exception("No se pudo guardar el tiempo de la fase %s", stage)

    def _run_stage(self, key: str, ctx: JobContext, llm: LLMServer, voice: dict) -> float | None:
        if key == "follow":
            return self._follow(ctx, llm)
        if key == "voiceprints":
            self._voiceprints(ctx)
            return None
        if key == "ingest":
            ingest.run(ctx)
            info = ctx.load("probe.json")
            with Session(engine) as s:
                v = s.get(Video, ctx.video_id)
                v.duration = info["duration"]
                v.recorded_at = datetime.fromisoformat(info["recorded_at"])
                s.add(v)
                s.commit()
        elif key == "frames":
            frames.run(ctx)
        elif key == "vision":
            vision.run(ctx, llm)
        elif key == "asr":
            asr.run_asr(ctx)
        elif key == "align":
            asr.run_align(ctx)
        elif key == "diarize":
            diarize.run(ctx)
        elif key == "names":
            names.run(ctx)
        elif key == "voices":
            voices.run(ctx)
        elif key == "identify":
            self._apply_overrides(ctx)
            identify.run(ctx, voice)
            with Session(engine) as s:
                services.persist_speakers(s, ctx.video_id, ctx.load("identities.json"))
                # De quién parece cada grupo de voz, con las huellas de otros vídeos
                person_names = {p.id: p.name for p in s.exec(select(Person))}
                splits = speaker_fix.split_suggestions(ctx.load("voices.json", {}).get("splits", {}),
                                                       services.voice_db(s, exclude_video=ctx.video_id),
                                                       ctx.settings.voice_match_threshold, person_names)
                speaker_fix.apply_splits(s, ctx.video_id, splits)
            self._load_names(ctx)
        elif key == "correct":
            self._apply_overrides(ctx)
            correct.run(ctx, llm)
        elif key == "analyze":
            analyze.run(ctx, llm)
            before = dict(ctx.speaker_names)
            with Session(engine) as s:
                services.apply_context_identities(s, ctx.video_id, ctx.load("context_identities.json", {}), ctx.people)
            self._load_names(ctx)
            # El resumen se escribió antes de saber quién era cada «Hablante N»: se usa el nombre propuesto,
            # igual que en la transcripción (al confirmar o cambiar el hablante se vuelve a sustituir)
            ctx.save("analysis.json", services.rename_speakers(ctx.load("analysis.json"), before, ctx.speaker_names))
        elif key == "learn":
            self._learn(ctx, llm)
        elif key == "publish":
            llm.stop()
            self._publish(ctx)
        return None

    def _follow(self, ctx: JobContext, llm: LLMServer) -> float:
        """Actualiza los seguimientos del vídeo. Es de mejor esfuerzo: un fallo deja el seguimiento
        desactualizado (con el motivo) pero no impide publicar el vídeo. Devuelve los minutos aplicados."""
        rebuild = set(ctx.options.get("follow_rebuild") or [])
        with Session(engine) as s:
            video = s.get(Video, ctx.video_id)
            if not FS.for_video(s, video.id):
                return 0.0
            # Recién analizado (aún sin publicar): el análisis y la transcripción están en la carpeta de trabajo
            fresh = not ctx.path("publish.done").exists()
            analysis = ctx.load("analysis.json") if fresh else video.analysis
            utts = ctx.load("corrected.json") if fresh else None

            def ask(system: str, user: str, schema: dict, thinking: bool = False) -> dict:
                ctx.check_cancel()
                llm.start()
                # Con el modo razonamiento, lo que piensa también cuenta en max_tokens
                return llm.chat_json(system, user, schema, max_tokens=16000 if thinking else 6000, thinking=thinking)

            try:
                minutes = FS.update_for_video(s, video, analysis or {}, rebuild, ask, ctx.report,
                                              only_rebuild=bool(ctx.options.get("only")), utts=utts)
                ctx.report(1.0, "Seguimientos actualizados")
                return minutes
            except Cancelled:
                raise
            except Exception as e:
                log.exception("Fallo al actualizar los seguimientos del vídeo %s", ctx.video_id)
                s.rollback()
                for f in FS.for_video(s, video.id):
                    if not ctx.options.get("only") or f.id in rebuild:
                        FS.mark_stale(s, f, FS.date_of(video), f"No se pudo actualizar con «{video.title}»: {e}")
                ctx.report(1.0, f"No se pudieron actualizar los seguimientos: {e}")
                return 0.0

    def _voiceprints(self, ctx: JobContext) -> None:
        """Huellas y muestras de voz de las personas confirmadas, con las intervenciones ya arregladas
        (`pipeline/voiceprints.py`). Sustituyen a las que tenía este vídeo."""
        self._apply_overrides(ctx)
        with Session(engine) as s:
            label_person = review.speakers_map(s, ctx.video_id)
            previous = services.voice_db(s, exclude_video=ctx.video_id)
        result: dict | None = {}
        if label_person:
            if not ctx.path("audio.wav").exists():
                if ctx.source_path and Path(ctx.source_path).is_file():
                    ingest.run(ctx)  # el audio de trabajo se borró (vídeos de antes de la revisión)
                else:
                    result = None
            if result is not None:
                result = voiceprints.run(ctx, label_person, previous, ctx.settings.voice_match_threshold,
                                         DATA_DIR / "voces")
        with Session(engine) as s:
            v = s.get(Video, ctx.video_id)
            if result is None:
                ctx.report(1.0, "No se encuentra el vídeo: se conservan sus voces")
            else:
                for e in s.exec(select(VoiceEmbedding).where(VoiceEmbedding.video_id == v.id)):
                    s.delete(e)
                for old in s.exec(select(VoiceSample).where(VoiceSample.video_id == v.id)):
                    if not any(r.get("sample") == old.path for r in result.values()):
                        Path(old.path).unlink(missing_ok=True)
                    s.delete(old)
                for pid, r in result.items():
                    s.add(VoiceEmbedding(person_id=pid, video_id=v.id, vector=r["vector"], doubtful=r["doubtful"],
                                         similarity=r["similarity"], seconds=r["seconds"]))
                    if r["sample"]:
                        s.add(VoiceSample(person_id=pid, video_id=v.id, path=r["sample"], seconds=r["sample_seconds"],
                                          score=r["score"]))
            v.voices_applied = label_person
            s.add(v)
            s.commit()

    def _learn(self, ctx: JobContext, llm: LLMServer) -> None:
        """Propuestas de conocimiento. Es de mejor esfuerzo: un fallo no impide publicar el vídeo."""
        try:
            in_video = {p["id"] for p in ctx.people if p.get("in_video")}
            with Session(engine) as s:
                rejected = KS.rejected_texts(s, (ctx.profile or {}).get("id"), in_video)
                pending = KS.pending_texts(s, ctx.video_id, (ctx.profile or {}).get("id"), in_video)
                sections = KS.has_pending_sections(s, (ctx.profile or {}).get("id"), ctx.video_id)
            proposals = learn.run(ctx, llm, rejected, pending, sections)
            with Session(engine) as s:
                stats = KS.merge_proposals(s, ctx.video_id, proposals, ctx.settings.voice_auto_threshold)
            ctx.report(1.0, f"{stats['nuevas']} propuestas nuevas, {stats['repetidas']} ya conocidas")
        except Cancelled:
            raise
        except Exception as e:
            log.exception("Fallo al aprender del vídeo %s", ctx.video_id)
            ctx.save("learn_error.json", {"error": str(e)})
            ctx.report(1.0, f"No se pudo aprender de este vídeo: {e}")

    def _load_names(self, ctx: JobContext) -> None:
        with Session(engine) as s:
            ctx.speaker_names = services.speaker_names(s, ctx.video_id)
            ctx.speaker_status = services.speaker_status(s, ctx.video_id)
            in_video = services.video_person_ids(s, ctx.video_id)
        for p in ctx.people:
            p["in_video"] = p["id"] in in_video

    def _publish(self, ctx: JobContext) -> None:
        s_ = ctx.settings
        analysis = ctx.load("analysis.json")
        utts = ctx.load("corrected.json")
        vision_res = ctx.load("vision.json", [])
        with Session(engine) as s:
            video = s.get(Video, ctx.video_id)
            video.title = analysis["titulo"]
            if video.folder and Path(video.folder).exists():
                folder = Path(video.folder)
            else:
                root = Path(s_.analyzed_dir)
                root.mkdir(parents=True, exist_ok=True)
                date = (video.recorded_at or video.created_at).strftime("%Y-%m-%d")
                folder = unique_dir(root, f"{date} - {safe_name(video.title)}")
                folder.mkdir(parents=True)
            ctx.report(0.1, "Copiando fotogramas")
            fdir = folder / "fotogramas"
            new_frames = list(ctx.path("frames").glob("*.jpg"))
            if new_frames and fdir.is_dir():
                shutil.rmtree(fdir)  # se han vuelto a elegir: que no queden fotogramas viejos
            fdir.mkdir(exist_ok=True)
            for f in new_frames:
                shutil.copy2(f, fdir / f.name)
            if ctx.path("thumbnail.jpg").exists():
                shutil.copy2(ctx.path("thumbnail.jpg"), folder / "miniatura.jpg")

            # Vídeo original: mover o copiar (solo la primera vez)
            if not (video.video_path and Path(video.video_path).exists() and Path(video.video_path).parent == folder):
                src = Path(video.source_path)
                dst = folder / src.name
                mode = ctx.options.get("file_mode") or s_.file_mode
                ctx.report(0.3, "Moviendo el vídeo" if mode == "move" else "Copiando el vídeo")
                if mode == "move":
                    shutil.move(str(src), str(dst))
                else:
                    shutil.copy2(src, dst)
                video.video_path = str(dst)

            video.folder = str(folder)
            video.analysis = analysis
            video.summary_md = analysis.get("resumen_breve", "")
            video.status = "done"

            # Transcripción y fotogramas en la base de datos
            for old in s.exec(select(Segment).where(Segment.video_id == video.id)):
                s.delete(old)
            for old in s.exec(select(Keyframe).where(Keyframe.video_id == video.id)):
                s.delete(old)
            for i, u in enumerate(utts):
                s.add(Segment(video_id=video.id, idx=i, start=u["start"], end=u["end"], speaker=u["speaker"],
                              voice=u.get("voice", ""),
                              text=u["text"], original_text=u.get("original_text", ""), corrections=u.get("corrections", [])))
            for v in vision_res:
                s.add(Keyframe(video_id=video.id, t=v["t"], path=str(fdir / v["file"]), scene_type=v.get("tipo_escena", ""),
                               description=v.get("descripcion", ""), visible_text=v.get("texto_relevante", ""),
                               participants=v.get("participantes", []), active_speaker=v.get("hablante_activo", "")))
            s.add(video)
            s.commit()
            s.refresh(video)
            removal.save_recovery(s, video, ctx.work_dir)
            ctx.report(0.8, "Generando documentos")
            services.export_video(s, video)
            services.index_video(s, video)
            for f in FS.for_video(s, video.id):
                FS.export(s, f)  # ahora ya tiene la carpeta del vídeo para enlazarla

    def _finish(self, job_id: int, status: str, message: str, error: str = "") -> None:
        with Session(engine) as s:
            job = s.get(Job, job_id)
            job.status, job.message, job.error, job.finished_at = status, message, error, datetime.now()
            took = (job.finished_at - job.started_at).total_seconds() if job.started_at else 0
            (log.warning if status == "error" else log.info)("Trabajo %s: %s, en %.0f s",
                                                             FINISH_LABELS.get(status, status), message, took)
            if status == "done":
                job.progress = 1.0
            video = s.get(Video, job.video_id)
            if status == "done" and video.folder:
                video.status = "done"  # también al repetir fases sueltas (p. ej. solo «learn»), sin publicar
            elif status != "done" and video.status == "processing":
                video.status = "error" if status == "error" else ("done" if video.folder else "pending")
            if status != "done" and video.review == review.APPLYING:
                video.review = review.PENDING
            s.add(job), s.add(video)
            s.commit()

    @staticmethod
    def _cleanup(wd: Path, keep_audio: bool = False) -> None:
        """Borra lo voluminoso (audio, fotogramas) y conserva los JSON para regenerar el análisis.

        `keep_audio`: el vídeo aún no está revisado y las huellas de voz se calculan al aplicar la revisión."""
        if not keep_audio:
            for name in ("audio.wav", "owner.wav"):
                (wd / name).unlink(missing_ok=True)
        shutil.rmtree(wd / "frames", ignore_errors=True)
        shutil.rmtree(wd / "samples", ignore_errors=True)


worker = Worker()
