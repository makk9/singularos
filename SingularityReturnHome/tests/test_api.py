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


def test_numbered_runs_and_history(tmp_path, monkeypatch):
    import telemetry.api as api

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    first = api.ensure_run("thruster_fault", 1, new=True)
    second = api.ensure_run("thruster_fault", 1, new=True)
    assert (first.name, second.name) == ("thruster_fault-seed1-r1", "thruster_fault-seed1-r2")
    rows = api.history("thruster_fault", 1, False)
    assert {r["run"] for r in rows} == {first.name, second.name}
    # Baseline runs on the same seed are identical, so their logs share a digest.
    assert len({r["digest"] for r in rows}) == 1
    assert all(r["outcome"] == "DOCKED" and r["pass"] for r in rows)
    assert api.run_path(first)[0][0] == 0.0


def test_live_session_streams_frames_and_saves_the_run(tmp_path, monkeypatch):
    import time

    import telemetry.api as api

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    session = api.start_live("thruster_fault", 1, False, 200.0)
    deadline = time.monotonic() + 60
    while not session.done and time.monotonic() < deadline:
        time.sleep(0.1)
    assert session.done and session.error is None
    assert session.summary["outcome"] == "DOCKED"
    assert session.frames and session.frames[-1]["phase"] == "DOCKED"
    assert (session.out / "replay.html").exists()
    # Paced: a ~550 s mission at 200x takes a few seconds, not instantly.
    assert session.frames[-1]["t"] > 400


def test_cancelled_live_session_stops_and_discards_the_run(tmp_path, monkeypatch):
    import time

    import telemetry.api as api

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    session = api.start_live("thruster_fault", 1, False, 20.0)
    deadline = time.monotonic() + 30
    while not session.frames and time.monotonic() < deadline:
        time.sleep(0.05)
    session.cancel()
    deadline = time.monotonic() + 10
    while not session.done and time.monotonic() < deadline:
        time.sleep(0.05)
    assert session.done and session.cancelled and session.error is None
    assert session.summary is None
    assert not session.out.exists()
    assert api.history() == []
