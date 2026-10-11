import pytest

from telemetry import api


def test_scenario_names_cover_both_scales():
    names = api.scenario_names()
    assert {"nominal", "thruster_fault", "orbital_strike_return", "orbital_strike_safe_orbit"} <= set(names)


def test_run_report_samples_track_and_events(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    out = api.ensure_run("thruster_fault", None)
    assert (out / "replay.html").exists()
    report = api.run_report(out)
    assert report["summary"]["outcome"] == "DOCKED"
    times = [p["t"] for p in report["track"]]
    assert times == sorted(times) and times[1] - times[0] == pytest.approx(api.TRACK_PERIOD_S)
    assert {"altitude_km", "perigee_km", "phase"} <= set(report["track"][0])
    assert any(e["type"] == "anomaly_detected" for e in report["events"])
