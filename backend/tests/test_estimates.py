"""Estimación de tiempos a partir de lo que han tardado las fases en este equipo."""

from app import estimates


def test_defaults_without_history(session):
    e = estimates.estimate(session, ["vision", "analyze"], duration=600, frames=40)
    assert e["stages"]["vision"] == 40 * estimates.DEFAULT_RATES["vision"]
    assert e["stages"]["analyze"] == 10 * estimates.DEFAULT_RATES["analyze"]
    assert e["total"] == sum(e["stages"].values())


def test_rate_weighs_runs_by_size(session):
    # Vídeo corto: cargar el modelo pesa mucho (60 s para 1 min). Vídeo largo: 300 s para 50 min
    estimates.record(session, None, None, "analyze", 60, duration=60, frames=0)
    estimates.record(session, None, None, "analyze", 300, duration=3000, frames=0)
    assert estimates.rates(session, ["analyze"])["analyze"] == 360 / 51  # ≈ 7 s/min, no la media de 60 y 6


def test_frames_guessed_from_duration(session):
    e = estimates.estimate(session, ["vision"], duration=3600, frames=None, max_frames=100)
    assert e["stages"]["vision"] == 100 * estimates.DEFAULT_RATES["vision"]  # 180 estimados, tope 100
