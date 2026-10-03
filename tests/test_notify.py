"""Alerts: events from two published entries, rendering, channels (no network), secret hygiene, idempotence."""

import json
import smtplib

import httpx
import pytest

from pfe_drai import notify
from pfe_drai.cli import main
from pfe_drai.config import load_settings
from tests.test_health import _entries

SECRETS = {
    "ALERT_SMTP_HOST": "smtp.secret-host.example",
    "ALERT_SMTP_PORT": "587",
    "ALERT_SMTP_USER": "user-secret-name",
    "ALERT_SMTP_PASSWORD": "pw-secret-value",
    "ALERT_EMAIL_FROM": "from-secret@example.org",
    "ALERT_EMAIL_TO": "a-secret@example.org, b-secret@example.org",
    "ALERT_WEBHOOK_URL": "https://hooks.example.org/services/SECRET-TOKEN",
}


@pytest.fixture(scope="module")
def cfg():
    return load_settings()


def _entry(day, alarm, regime="expansion", since=None):
    return {"date": day, "regime": regime, "p_stress": 0.62 if alarm else 0.08, "alarm_on": alarm, "alarm_since": since}


def _folder(tmp_path, states, health=None):
    """A real track_record/ folder whose days carry the given (alarm_on, regime) states."""
    days = [f"2026-09-{d:02d}" for d in (14, 15, 16, 17, 18)][: len(states)]
    folder = _entries(tmp_path / "track_record", days)
    import csv
    import hashlib

    previous, rows = "", []
    for day, (alarm, regime) in zip(days, states, strict=True):
        path = folder / f"{day}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(regime=regime, alarm={"on": alarm, "since": day if alarm else None, "score": 0.6 if alarm else 0.1})
        payload["probabilities"] = {"stress": 0.62 if alarm else 0.08}
        payload["previous_sha256"] = previous
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append([day, regime, "0.5", "combined", "fred", previous])
    with (folder / "index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "regime", "p_regime", "model", "data_provider", "sha256"])
        writer.writerows(rows)
    for day, record in (health or {}).items():
        (folder / "health").mkdir(exist_ok=True)
        (folder / "health" / f"{day}.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


# ---------------------------------------------------------------- detection
def test_off_then_on_is_one_alarm_on():
    events = notify.detect_events(_entry("2026-09-14", False), _entry("2026-09-15", True, "stress", "2026-09-15"))
    assert [e.type for e in events] == ["alarm_on", "regime_change"]
    only = notify.detect_events(_entry("2026-09-14", False), _entry("2026-09-15", True), events=("alarm_on",))
    assert [e.type for e in only] == ["alarm_on"]


def test_on_then_off_is_one_alarm_off():
    events = notify.detect_events(_entry("a", True), _entry("b", False))
    assert [e.type for e in events] == ["alarm_off"]


def test_equal_states_and_first_day_give_nothing():
    assert notify.detect_events(_entry("a", True), _entry("b", True)) == []
    assert notify.detect_events(_entry("a", False), _entry("b", False)) == []
    assert notify.detect_events(None, _entry("b", True)) == []
    assert notify.detect_events(_entry("a", None), _entry("b", True)) == []  # unknown state: no guess


# ---------------------------------------------------------------- rendering
@pytest.mark.parametrize("kind", notify.EVENTS)
@pytest.mark.parametrize("lang", ["fr", "en", "both"])
def test_render_is_complete_and_generic(cfg, kind, lang):
    entry, before = _entry("2026-09-15", True, "stress", "2026-09-15"), _entry("2026-09-14", False, "slowdown")
    subject, text, html = notify.render(notify.Event(kind, "2026-09-15", entry, before), lang, cfg)
    for part in (subject, text, html):
        assert "{" not in part and "}" not in part  # every placeholder filled
    assert cfg["publish"]["pages_url"] in text
    assert "62" in text
    words = ("not investment advice", "pas un conseil") if lang == "en" else ("ni un conseil",)
    assert any(w in text.lower() or w in text for w in words) or lang == "both"
    for banned in ("buy", "sell", "reduce your", "achetez", "vendez", "réduisez"):
        assert banned not in text.lower()


def test_render_marks_degraded_and_test(cfg):
    event = notify.Event(
        "alarm_on", "2026-09-15", _entry("2026-09-15", True, "stress", "2026-09-15"), _entry("x", False), "stale"
    )
    _, text, _ = notify.render(event, "en", cfg)
    assert "degraded" in text and "stale" not in text  # the reason stays in the public health record
    subject, text, _ = notify.render(event, "en", cfg, test=True)
    assert subject.startswith("[TEST]") and "test message" in text


# ---------------------------------------------------------------- channels
class FakeSMTP:
    sent = []
    log = []

    def __init__(self, host, port, timeout=None):
        FakeSMTP.log.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.log.append(("login", user))

    def send_message(self, message):
        FakeSMTP.sent.append(message)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.log = [], []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_email_one_message_per_recipient_over_tls(smtp):
    notify.send_email("subject", "text", "<p>text</p>", ["a@x.org", "b@x.org"], SECRETS)
    assert [m["To"] for m in smtp.sent] == ["a@x.org", "b@x.org"]  # recipients never see one another
    assert ("starttls",) in smtp.log and ("login", "user-secret-name") in smtp.log
    assert smtp.sent[0].get_body(("plain",)).get_content().strip() == "text"


def test_webhook_payload_is_slack_compatible():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200)

    notify.send_webhook("S", "T", SECRETS, httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen[0]["text"] == "*S*\n\nT" and seen[0]["subject"] == "S" and seen[0]["body"] == "T"


def test_a_failing_channel_logs_only_its_name_and_class(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("could not reach https://hooks.example.org/services/SECRET-TOKEN")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    result = notify.deliver("s", "t", "h", ["webhook"], SECRETS, client=client)
    assert result == {"webhook": "ConnectError"}


def test_channels_need_settings_and_environment(cfg):
    assert notify.configured_channels(cfg, {}) == []
    assert notify.configured_channels(cfg, SECRETS) == ["email", "webhook"]
    off = {**cfg, "alerts": {**cfg["alerts"], "channels": []}}
    assert notify.configured_channels(off, SECRETS) == []


def test_subscriber_source_is_swappable(smtp):
    class Accounts:
        def emails(self):
            return ["account@x.org"]

    notify.deliver("s", "t", "h", ["email"], SECRETS, source=Accounts())
    assert [m["To"] for m in smtp.sent] == ["account@x.org"]


def test_no_secret_in_settings_or_rendered_text(cfg):
    blob = json.dumps(cfg["alerts"])
    entry = _entry("2026-09-15", True, "stress", "2026-09-15")
    _, text, html = notify.render(notify.Event("alarm_on", "2026-09-15", entry, _entry("x", False)), "both", cfg)
    for value in SECRETS.values():
        assert value not in blob + text + html


# ---------------------------------------------------------------- the daily run
def test_run_sends_once_then_is_idempotent(cfg, tmp_path, smtp):
    folder = _folder(tmp_path, [(False, "expansion"), (True, "stress")])
    lines = []
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    code = notify.run(folder, cfg, "both", False, False, env=SECRETS, client=client, out=lines.append)
    assert code == 0 and len(sent) == 2 and len(smtp.sent) == 4  # alarm_on + regime_change, 2 recipients
    ledger = json.loads((folder / "alerts" / "2026-09-15.json").read_text(encoding="utf-8"))
    assert len(ledger["sent"]) == 4
    for value in SECRETS.values():
        assert value not in json.dumps(ledger) + "\n".join(lines)
    notify.run(folder, cfg, "both", False, False, env=SECRETS, client=client, out=lines.append)
    assert len(sent) == 2 and len(smtp.sent) == 4  # the manual re-run sent nothing
    notify.run(folder, cfg, "both", False, True, env=SECRETS, client=client, out=lines.append)  # --force
    assert len(sent) == 4


def test_run_resends_only_the_failed_channel(cfg, tmp_path, smtp):
    folder = _folder(tmp_path, [(True, "stress"), (False, "stress")])
    calls = []
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500)))
    assert notify.run(folder, cfg, "en", False, False, env=SECRETS, client=ok, out=lambda _: None) == 1
    assert len(smtp.sent) == 2 and len(calls) == 1
    good = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200)))
    assert notify.run(folder, cfg, "en", False, False, env=SECRETS, client=good, out=lambda _: None) == 0
    assert len(smtp.sent) == 2 and len(calls) == 2  # email was not sent twice


def test_run_nothing_to_send(cfg, tmp_path, smtp):
    lines = []
    assert notify.run(_folder(tmp_path / "a", [(False, "expansion")]), cfg, "en", False, False, SECRETS, out=lines.append) == 0
    assert "fewer than two" in lines[-1]
    same = _folder(tmp_path / "b", [(False, "expansion"), (False, "expansion")])
    assert notify.run(same, cfg, "en", False, False, SECRETS, out=lines.append) == 0
    assert "no change" in lines[-1] and not smtp.sent


def test_run_without_secrets_succeeds(cfg, tmp_path):
    folder = _folder(tmp_path, [(False, "expansion"), (True, "stress")])
    lines = []
    assert notify.run(folder, cfg, "en", False, False, env={}, out=lines.append) == 0
    assert lines == ["no channel configured: nothing sent"]
    assert not (folder / "alerts").exists()


def test_dry_run_prints_the_message_and_touches_nothing(cfg, tmp_path, smtp):
    folder = _folder(tmp_path, [(True, "stress"), (False, "slowdown")])
    lines = []
    assert notify.run(folder, cfg, "en", True, False, env=SECRETS, out=lines.append) == 0
    assert "Stress alarm OFF" in "\n".join(lines) and "not sent" in lines[0]
    assert not smtp.log and not (folder / "alerts").exists()


def test_degraded_day_is_labelled_not_dropped(cfg, tmp_path):
    record = {"status": "warning", "checks": [{"name": "sources", "status": "warning", "message": "stale"}]}
    folder = _folder(tmp_path, [(False, "expansion"), (True, "stress")], {"2026-09-15": record})
    events, _ = notify.pending_events(folder, cfg)
    assert {e.degraded for e in events} == {"sources: stale"}


def test_cli_dry_run_and_test_without_channels(cfg, tmp_path, capsys, monkeypatch):
    for name in notify.ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    folder = _folder(tmp_path, [(False, "expansion"), (True, "stress")])
    with pytest.raises(SystemExit) as stop:
        main(["notify", "--dry-run", "--language", "en", "--folder", str(folder)])
    assert stop.value.code == 0 and "Stress alarm ON" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        main(["notify", "--test"])
    assert stop.value.code == 0 and "no channel configured" in capsys.readouterr().out


def test_alerts_do_not_change_the_model_fingerprint(cfg):
    from pfe_drai.publish.snapshot import config_fingerprint

    assert config_fingerprint(cfg).startswith("7d25ca34")


def test_email_failure_names_the_step_and_class_only(monkeypatch):
    class Refusing(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad pw-secret-value for user-secret-name")

    monkeypatch.setattr(smtplib, "SMTP", Refusing)
    result = notify.deliver("s", "t", "h", ["email"], SECRETS)
    assert result == {"email": "SMTPAuthenticationError at login"}

    def cut(*args, **kwargs):
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    monkeypatch.setattr(smtplib, "SMTP", cut)
    assert notify.deliver("s", "t", "h", ["email"], SECRETS) == {"email": "SMTPServerDisconnected at connect"}
