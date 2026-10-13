"""Tests for the tvmirror wrapper (pure logic only; no TV, no GPU needed)."""
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "tvmirror"


@pytest.fixture()
def tv(tmp_path, monkeypatch):
    monkeypatch.setenv("TVMIRROR_CONFIG", str(tmp_path / "cfg"))
    monkeypatch.setenv("TVMIRROR_CACHE", str(tmp_path / "cache"))
    loader = importlib.machinery.SourceFileLoader("tvmirror_mod", str(SCRIPT))
    spec = importlib.util.spec_from_loader("tvmirror_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- profiles ----
def test_profile_mac_beats_name_rule(tv):
    profiles = {"by_mac": {"AA:BB:CC:DD:EE:FF": {"flags": ["--x"]}},
                "by_name": [{"match": "^Von", "flags": ["--y"]}]}
    assert tv.resolve_profile("aa:bb:cc:dd:ee:ff", "Von TV", profiles) == (
        ["--x"], "saved for AA:BB:CC:DD:EE:FF")


def test_profile_name_rule_case_insensitive_first_wins(tv):
    profiles = {"by_mac": {}, "by_name": [
        {"match": "tv", "flags": ["--first"]}, {"match": "von", "flags": ["--second"]}]}
    flags, src = tv.resolve_profile("00:00:00:00:00:01", "VON-TV", profiles)
    assert flags == ["--first"] and "name rule" in src


def test_profile_bad_regex_is_ignored_not_fatal(tv):
    profiles = {"by_mac": {}, "by_name": [{"match": "(", "flags": ["--a"]},
                                          {"match": "ok", "flags": ["--b"]}]}
    assert tv.resolve_profile("00:00:00:00:00:01", "ok", profiles)[0] == ["--b"]


def test_profile_no_match(tv):
    assert tv.resolve_profile("00:00:00:00:00:01", "x", {"by_mac": {}, "by_name": []}) == ([], "")


def test_learn_profile_roundtrip_and_skips_defaults(tv):
    tv.learn_profile("aa:bb:cc:dd:ee:ff", "Some TV", [])
    assert not tv.PROFILES_FILE.exists()
    tv.learn_profile("aa:bb:cc:dd:ee:ff", "Some TV", ["--wfd-go-intent", "15"])
    data = tv.load_profiles()
    assert data["by_mac"]["AA:BB:CC:DD:EE:FF"]["flags"] == ["--wfd-go-intent", "15"]


def test_corrupt_profiles_file_does_not_crash(tv):
    tv.CONFIG.mkdir(parents=True)
    tv.PROFILES_FILE.write_text("{nope")
    assert tv.load_profiles() == {"by_mac": {}, "by_name": []}


# ------------------------------------------------------------------- plan ----
def test_plan_without_autofix_is_single_attempt(tv):
    assert tv.plan_attempts([], False) == [([], "defaults")]
    assert tv.plan_attempts(["--a"], False) == [(["--a"], "saved profile")]


def test_plan_autofix_starts_with_saved_profile_and_dedups(tv):
    plan = tv.plan_attempts(["--wfd-p2p-backend", "wpas"], True)
    assert plan[0] == (["--wfd-p2p-backend", "wpas"], "saved profile")
    keys = [tuple(f) for f, _ in plan]
    assert len(keys) == len(set(keys))                 # no repeats
    assert tuple() in keys                             # defaults still tried


def test_plan_autofix_last_resort_is_degrade(tv):
    assert "--output-res" in tv.plan_attempts([], True)[-1][0]


def test_every_ladder_flag_exists_upstream(tv):
    """Guard against typos: every flag we may pass must exist in FluxCast's CLI."""
    import os
    fluxcast_src = os.environ.get("FLUXCAST_SRC")
    if not fluxcast_src:
        pytest.skip("FluxCast source tree not available (set FLUXCAST_SRC)")
    main_py = Path(fluxcast_src).read_text()
    for flags, _ in tv.FIX_LADDER:
        for f in flags:
            if f.startswith("--"):
                assert f'"{f}"' in main_py, f


# ----------------------------------------------------------------- session ----
def test_session_ok_rules(tv):
    assert tv.session_ok(0, 1, False)           # clean exit
    assert tv.session_ok(1, 999, False)         # lived long enough
    assert tv.session_ok(1, 1, True)            # user pressed ctrl-c
    assert not tv.session_ok(1, 3, False)       # died fast => failure


class FakeProc:
    def __init__(self, rc, raise_kb=False):
        self.rc, self.raise_kb, self.signalled = rc, raise_kb, False

    def wait(self, timeout=None):
        if self.raise_kb and not self.signalled:
            raise KeyboardInterrupt
        return self.rc

    def send_signal(self, sig):
        self.signalled = True

    def kill(self):
        pass


def test_run_stream_measures_time_and_interrupts(tv):
    ticks = iter([100.0, 107.5])
    rc, secs, intr = tv.run_stream(["x"], popen=lambda c: FakeProc(3), clock=lambda: next(ticks))
    assert (rc, secs, intr) == (3, 7.5, False)
    ticks = iter([0.0, 2.0])
    rc, secs, intr = tv.run_stream(["x"], popen=lambda c: FakeProc(0, raise_kb=True),
                                   clock=lambda: next(ticks))
    assert intr is True


# ----------------------------------------------------------------- doctor ----
DOCTOR = """FluxCast doctor
  ok    iw P2P            p2p-dev-wlan0
  warn  ffmpeg encoders   libx264 only
  fail  nothing           broken
"""


def test_parse_doctor(tv):
    rep = tv.parse_doctor(DOCTOR)
    assert rep["iw P2P"] == ("ok", "p2p-dev-wlan0")
    assert rep["ffmpeg encoders"][0] == "warn"
    assert rep["nothing"][0] == "fail"


def test_doctor_cache_fresh_stale_and_env(tv, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    rep = {"iw P2P": ("ok", "x")}
    tv._doctor_cache_store(rep, now=1000.0)
    assert tv._doctor_cache_load(now=1000.0 + tv.DOCTOR_TTL - 1) == rep
    assert tv._doctor_cache_load(now=1000.0 + tv.DOCTOR_TTL + 1) is None
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-2")       # session changed
    assert tv._doctor_cache_load(now=1000.0) is None


def test_doctor_cache_garbage_is_a_miss(tv):
    tv.CACHE.mkdir(parents=True)
    tv.DOCTOR_CACHE.write_text("not json")
    assert tv._doctor_cache_load() is None


# --------------------------------------------------------------- encoders ----
def test_probe_hw_encoders(tv, monkeypatch):
    monkeypatch.setattr(tv.shutil, "which", lambda n: "/usr/bin/" + n)

    def fake_run(cmd, **kw):
        ok = cmd[-1] in ("vah264enc", "nvh264enc")
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "")
    assert tv.probe_hw_encoders(run=fake_run) == ["vah264enc", "nvh264enc"]


def test_probe_hw_encoders_without_gst(tv, monkeypatch):
    monkeypatch.setattr(tv.shutil, "which", lambda n: None)
    assert tv.probe_hw_encoders() == []


# ---------------------------------------------------------------- peers ----
def test_parse_peers(tv):
    out = "[FluxCast WFD] WFD capability data detected\n  [0] aa:bb:cc:dd:ee:ff  Living Room TV via wlan0\n"
    peers = tv.parse_peers(out)
    assert peers == [{"mac": "AA:BB:CC:DD:EE:FF", "name": "Living Room TV", "wfd": True}]


def test_profile_set_cli_roundtrip(tmp_path):
    env = {"TVMIRROR_CONFIG": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(SCRIPT), "profile-set", "aa:bb:cc:dd:ee:ff",
                        "--", "--wfd-go-intent", "15"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads((tmp_path / "profiles.json").read_text())
    assert data["by_mac"]["AA:BB:CC:DD:EE:FF"]["flags"] == ["--wfd-go-intent", "15"]
    r = subprocess.run([sys.executable, str(SCRIPT), "profile-forget", "aa:bb:cc:dd:ee:ff"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads((tmp_path / "profiles.json").read_text())["by_mac"] == {}


# ------------------------------------------------- end-to-end with a fake sink ----
FAKE_FLUX = r'''
import sys, time
a = sys.argv[1:]
if "--help" in a:
    print("--wfd-go-intent --wfd-p2p-backend --wfd-p2p-channel --wfd-aosp-pmt-pid --fps --output-res")
elif "--doctor" in a:
    print("  ok    iw P2P            fine")
    print("  ok    screen capture    fine")
    print("  ok    ffmpeg encoders   libx264")
elif "--wfd-scan" in a:
    print("[FluxCast WFD] WFD capability data detected")
    print("  [0] 11:22:33:44:55:66  Quirky TV via wlan0")
else:
    # Only survives when we are the P2P group owner (go-intent 15).
    ok = "--wfd-go-intent" in a and a[a.index("--wfd-go-intent") + 1] == "15"
    print("RUN", " ".join(a), flush=True)
    if ok:
        time.sleep(2)
        sys.exit(0)
    sys.exit(1)
'''


def _e2e(tmp_path, *args, stable="1"):
    flux = tmp_path / "flux" / "src"
    flux.mkdir(parents=True, exist_ok=True)
    (flux / "main.py").write_text(FAKE_FLUX)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "TVMIRROR_FLUXCAST": str(tmp_path / "flux"),
           "TVMIRROR_CONFIG": str(tmp_path / "cfg"), "TVMIRROR_CACHE": str(tmp_path / "cache"),
           "TVMIRROR_STABLE_SECONDS": stable, "NO_COLOR": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                          capture_output=True, text=True, timeout=120)


def test_e2e_autofix_finds_and_remembers_working_flags(tmp_path):
    r = _e2e(tmp_path, "run", "--peer", "11:22:33:44:55:66", "--auto-fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "retry" in r.stdout
    prof = json.loads((tmp_path / "cfg" / "profiles.json").read_text())
    assert prof["by_mac"]["11:22:33:44:55:66"]["flags"] == ["--wfd-go-intent", "15"]
    # Second run goes straight to the remembered flags: no retries needed.
    r2 = _e2e(tmp_path, "run", "--peer", "11:22:33:44:55:66")
    assert r2.returncode == 0 and "retry" not in r2.stdout
    assert "--wfd-go-intent 15" in r2.stdout


def test_e2e_without_autofix_fails_fast_and_learns_nothing(tmp_path):
    r = _e2e(tmp_path, "run", "--peer", "11:22:33:44:55:66")
    assert r.returncode == 1
    assert not (tmp_path / "cfg" / "profiles.json").exists()


def test_e2e_peer_given_skips_wrapper_scan(tmp_path):
    r = _e2e(tmp_path, "run", "--peer", "11:22:33:44:55:66", "--auto-fix")
    assert "skipping the wrapper scan" in r.stdout


def test_e2e_doctor_is_cached_between_runs(tmp_path):
    _e2e(tmp_path, "run", "--peer", "11:22:33:44:55:66", "--dry-run")
    assert (tmp_path / "cache" / "doctor.json").exists()
