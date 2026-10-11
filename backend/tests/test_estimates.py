"""Estimación de tiempos a partir de lo que han tardado las fases en este equipo."""

from app import estimates


def test_defaults_without_history(session):
    e = estimates.estimate(session, ["vision", "analyze"], duration=600, frames=40)
    assert e["stages"]["vision"] == 40 * estimates.DEFAULT_RATES["vision"]
    assert e["stages"]["analyze"] == 10 * estimates.DEFAULT_RATES["analyze"]
    assert e["total"] == sum(e["stages"].values())


def test_median_of_recent_runs(session):
    for seconds in (100, 200, 1000):  # 10 fotogramas cada vez: 10, 20 y 100 s/fotograma
        estimates.record(session, None, None, "vision", seconds, duration=60, frames=10)
    assert estimates.rates(session, ["vision"])["vision"] == 20


def test_frames_guessed_from_duration(session):
    e = estimates.estimate(session, ["vision"], duration=3600, frames=None, max_frames=100)
    assert e["stages"]["vision"] == 100 * estimates.DEFAULT_RATES["vision"]  # 180 estimados, tope 100
