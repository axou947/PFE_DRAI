"""Messages when the published stress alarm switches on or off (docs/ALERTS.md).

Everything here starts from two *published* entries of track_record/ (never a recomputed number), so
what people are told is exactly what the public page shows. Addresses, passwords and URLs come from
the environment only; neither the repository, the logs nor the rendered text ever holds them.

Recipients come from a `SubscriberSource`. The first one reads a list from the environment; a later
accounts feature only has to provide another source (same `emails()` method).
"""

import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Protocol

import httpx

from .health import HEALTH_DIR, OK
from .i18n import fmt_date, fmt_pct, t

EVENTS = ("alarm_on", "alarm_off", "regime_change")
LEDGER_DIR = "alerts"
ENV_NAMES = (
    "ALERT_SMTP_HOST",
    "ALERT_SMTP_PORT",
    "ALERT_SMTP_USER",
    "ALERT_SMTP_PASSWORD",
    "ALERT_EMAIL_FROM",
    "ALERT_EMAIL_TO",
    "ALERT_WEBHOOK_URL",
)


@dataclass(frozen=True)
class Event:
    type: str
    day: str
    entry: dict  # the published entry of that day (read_live format)
    previous: dict
    degraded: str | None = None  # why the day's data was degraded, when the health record says so


# ---------------------------------------------------------------- detection
def detect_events(previous: dict | None, today: dict | None, events=EVENTS) -> list[Event]:
    """Events between two consecutive published entries; none on the first day or when a state is unknown."""
    if not previous or not today:
        return []
    found = []
    before, after = previous.get("alarm_on"), today.get("alarm_on")
    if before is not None and after is not None and before != after:
        found.append("alarm_on" if after else "alarm_off")
    if previous.get("regime") and today.get("regime") and previous["regime"] != today["regime"]:
        found.append("regime_change")
    return [Event(kind, today["date"], today, previous) for kind in found if kind in events]


def degraded_reason(folder: Path, day: str) -> str | None:
    """The data-health record of the day (written by `publish`): a short reason when it found a problem."""
    path = Path(folder) / HEALTH_DIR / f"{day}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    problems = [c for c in record.get("checks", []) if c.get("status") != OK]
    return "; ".join(f"{c['name']}: {c['message']}" for c in problems[:3]) if problems else None


# ---------------------------------------------------------------- rendering
def _entry_regime(entry: dict, lang: str) -> str:
    return t(f"regime.{entry['regime']}", lang)


def render(event: Event, lang: str, settings: dict, test: bool = False) -> tuple[str, str, str]:
    """(subject, plain text, html) in `lang` ('fr', 'en' or 'both': French then English)."""
    if lang == "both":
        parts = [render(event, code, settings, test) for code in ("fr", "en")]
        subject = " / ".join(p[0] for p in parts)
        text = "\n\n----------\n\n".join(p[1] for p in parts)
        html = "<hr>".join(p[2] for p in parts)
        return subject, text, html
    entry = event.entry
    p_stress = entry.get("p_stress")
    fields = {
        "date": fmt_date(event.day, lang),
        "regime": _entry_regime(entry, lang),
        "old_regime": _entry_regime(event.previous, lang),
        "p_stress": fmt_pct(p_stress, lang) if p_stress is not None else "n/a",
        "threshold": fmt_pct(settings["validation"]["stress_probability_threshold"], lang),
        "confirm_days": settings["validation"]["confirm_days"],
        "since": fmt_date(entry["alarm_since"], lang) if entry.get("alarm_since") else "n/a",
        "url": settings["publish"].get("pages_url", ""),
    }
    lines = [
        t(f"notify.{event.type}.body", lang, **fields),
        t("notify.state", lang, **fields),
        t("notify.page", lang, **fields),
    ]
    if event.degraded:
        lines.append(t("notify.degraded", lang))  # the reason itself is in the public health record, not here
    lines += [t("notify.disclaimer", lang), t("notify.unsubscribe", lang)]
    subject = t(f"notify.{event.type}.subject", lang, **fields)
    if test:
        subject = f"[{t('notify.test.label', lang)}] {subject}"
        lines.insert(0, t("notify.test.body", lang))
    html = "".join(f"<p>{escape(line)}</p>" for line in lines)
    return subject, "\n\n".join(lines), html


# ---------------------------------------------------------------- recipients and channels
class SubscriberSource(Protocol):
    def emails(self) -> list[str]: ...


class EnvSubscribers:
    """First source: a comma list in ALERT_EMAIL_TO (a GitHub secret). A user-accounts source replaces it."""

    def __init__(self, env=None):
        self.env = os.environ if env is None else env

    def emails(self) -> list[str]:
        return [a.strip() for a in self.env.get("ALERT_EMAIL_TO", "").split(",") if a.strip()]


def _error_name(exc: BaseException) -> str:
    return type(exc).__name__  # never the message: it can hold a host, an address or a URL


class StageError(Exception):
    """A send step failed: keeps only the step name and the error class (never the message)."""

    def __init__(self, stage: str, cause: BaseException):
        super().__init__(f"{_error_name(cause)} at {stage}")


def send_email(subject: str, text: str, html: str, recipients: list[str], env) -> None:
    host, sender = env.get("ALERT_SMTP_HOST", ""), env.get("ALERT_EMAIL_FROM", "")
    port = int(env.get("ALERT_SMTP_PORT") or 587)
    if not (host and sender and recipients):
        raise ValueError("email channel not configured")
    for to in recipients:  # one message each: recipients never see one another
        message = EmailMessage()
        message["Subject"], message["From"], message["To"] = subject, sender, to
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        stage = "connect"
        try:
            factory = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
            with factory(host, port, timeout=30) as server:
                if port != 465:
                    stage = "starttls"
                    server.starttls(context=ssl.create_default_context())
                if env.get("ALERT_SMTP_USER"):
                    stage = "login"
                    server.login(env["ALERT_SMTP_USER"], env.get("ALERT_SMTP_PASSWORD", ""))
                stage = "send"
                server.send_message(message)
        except Exception as exc:  # noqa: BLE001
            raise StageError(stage, exc) from None


def send_webhook(subject: str, text: str, env, client: httpx.Client | None = None) -> None:
    url = env.get("ALERT_WEBHOOK_URL", "")
    if not url:
        raise ValueError("webhook channel not configured")
    # `text` is Slack/Discord-compatible; `subject` and `body` serve a plain JSON consumer.
    payload = {"text": f"*{subject}*\n\n{text}", "subject": subject, "body": text}
    own = client or httpx.Client(timeout=20)
    try:
        own.post(url, json=payload).raise_for_status()
    finally:
        if client is None:
            own.close()


def configured_channels(settings: dict, env) -> list[str]:
    """Channels named in the settings AND with their environment set."""
    names = settings["alerts"].get("channels") or []
    ready = {
        "email": bool(env.get("ALERT_SMTP_HOST") and env.get("ALERT_EMAIL_FROM") and EnvSubscribers(env).emails()),
        "webhook": bool(env.get("ALERT_WEBHOOK_URL")),
    }
    return [name for name in names if ready.get(name)]


def deliver(subject, text, html, channels, env, source: SubscriberSource | None = None, client=None) -> dict[str, str]:
    """Send on each channel; returns {channel: 'sent' | error class}. One failing channel never stops the others."""
    source = source or EnvSubscribers(env)
    result = {}
    for name in channels:
        try:
            if name == "email":
                send_email(subject, text, html, source.emails(), env)
            elif name == "webhook":
                send_webhook(subject, text, env, client)
            else:
                raise ValueError("unknown channel")
            result[name] = "sent"
        except Exception as exc:  # noqa: BLE001 - alerting must never raise into the daily job
            result[name] = str(exc) if isinstance(exc, StageError) else _error_name(exc)
    return result


# ---------------------------------------------------------------- the daily run
def ledger_path(folder: Path, day: str) -> Path:
    return Path(folder) / LEDGER_DIR / f"{day}.json"


def pending_events(folder: Path, settings: dict) -> tuple[list[Event], str | None]:
    """Events of the latest published day not yet sent, and a reason when there are none."""
    from .publish.record import read_live

    live = read_live(Path(folder))
    if len(live.entries) < 2:
        return [], "fewer than two published days: nothing to compare"
    previous, today = live.entries[-2], live.entries[-1]
    wanted = tuple(settings["alerts"].get("notify", {}).get("events", EVENTS))
    events = detect_events(previous, today, wanted)
    if not events:
        return [], f"no change on {today['date']}: nothing to send"
    reason = degraded_reason(folder, today["date"])
    return [Event(e.type, e.day, e.entry, e.previous, reason) for e in events], None


def run(folder: Path, settings: dict, lang: str, dry_run: bool, force: bool, env=None, client=None, out=print) -> int:
    """Send the latest day's events. Returns 0 (also when nothing is due), 1 when a configured channel failed."""
    env = os.environ if env is None else env
    events, why_not = pending_events(folder, settings)
    if why_not:
        out(why_not)
        return 0
    day = events[0].day
    ledger = ledger_path(folder, day)
    done = set() if force or dry_run else _already_sent(ledger)
    channels = configured_channels(settings, env)
    if not channels and not dry_run:
        out("no channel configured: nothing sent")
        return 0
    failed = False
    sent = []
    for event in events:
        subject, text, html = render(event, lang, settings)
        if dry_run:
            out(f"--- dry run, not sent: {event.type} ---\nSubject: {subject}\n\n{text}\n")
            continue
        todo = [name for name in channels if (event.type, name) not in done]
        if not todo:
            out(f"{event.type}: already sent on {day} (track_record/{LEDGER_DIR}/{day}.json); --force sends again")
            continue
        for name, status in deliver(subject, text, html, todo, env, client=client).items():
            out(f"{event.type} -> {name}: {status}")
            failed |= status != "sent"
            if status == "sent":
                sent.append({"event": event.type, "channel": name})
    if sent:  # no address, no URL: only what was sent where
        ledger.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted({(r["event"], r["channel"]) for r in sent} | done)
        body = {"date": day, "sent": [{"event": e, "channel": c} for e, c in rows]}
        ledger.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failed else 0


def _already_sent(ledger: Path) -> set[tuple[str, str]]:
    try:
        return {(r["event"], r["channel"]) for r in json.loads(ledger.read_text(encoding="utf-8"))["sent"]}
    except (OSError, ValueError, KeyError):
        return set()


def send_test(settings: dict, lang: str, env=None, client=None, out=print) -> int:
    """A clearly labelled test message through the configured channels (nothing is recorded)."""
    env = os.environ if env is None else env
    channels = configured_channels(settings, env)
    if not channels:
        out("no channel configured: set alerts.channels in the settings and the ALERT_* variables (docs/ALERTS.md)")
        return 0
    sample = {"date": "2000-01-03", "regime": "stress", "p_stress": 0.62, "alarm_on": True, "alarm_since": "2000-01-03"}
    earlier = {"date": "1999-12-31", "regime": "slowdown", "alarm_on": False}
    subject, text, html = render(Event("alarm_on", sample["date"], sample, earlier), lang, settings, test=True)
    failed = False
    for name, status in deliver(subject, text, html, channels, env, client=client).items():
        out(f"test -> {name}: {status}")
        failed |= status != "sent"
    return 1 if failed else 0


def preview(folder: Path, settings: dict, lang: str) -> tuple[str, str, str] | None:
    """What would be sent for the latest published day, for the app's Alerts tab (None when nothing changed)."""
    events, _ = pending_events(folder, settings)
    return render(events[0], lang, settings) if events else None
