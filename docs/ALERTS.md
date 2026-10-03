# Alerts: a message when the stress alarm switches

One message the evening the **published** stress alarm turns on or off, or the regime changes. It is
built from two entries of `track_record/` (the day and the one before), never from a recomputed number,
so it says exactly what the public page says. It does not touch the daily record, the backtest record,
the page or the settings fingerprint.

## What is sent, and when

| Event | When |
|---|---|
| `alarm_on` | the alarm was off on the previous published day and is on today |
| `alarm_off` | on yesterday, off today |
| `regime_change` | the published regime differs from the previous day's |

No change, a first day, or an unknown state: nothing is sent. Content: what changed, the regime and
estimated probability of stress, the alarm rule (threshold, confirmation days, since-date), the link to
the public page, and the sentence that this is a generic market risk level, not investment advice. No
price, no instruction to trade. A day whose data the health check flagged as degraded is **still sent**
(a late or missing alarm would be worse) with one line saying so; the details stay on the public page.

Language: `alerts.notify.language` in `config/settings.yaml` (`fr`, `en` or `both`, default `both`: French
then English), or `--language` on the command.

## Channels

Named in `alerts.channels` (`email`, `webhook`); a channel sends only when its variables are set. Variables
live in the environment (GitHub Actions secrets in the daily job), never in a file:

| Variable | Used by | Meaning |
|---|---|---|
| `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT` | email | server and port (587 STARTTLS by default, 465 for implicit TLS) |
| `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD` | email | login (app password, see below) |
| `ALERT_EMAIL_FROM` | email | sender address |
| `ALERT_EMAIL_TO` | email | recipients, comma separated; one message each, nobody sees the others |
| `ALERT_WEBHOOK_URL` | webhook | Slack, Discord (add `/slack` to its URL) or any endpoint taking JSON |

The webhook receives `{"text": "*subject*\n\nbody", "subject": "...", "body": "..."}`.

**Gmail:** turn on 2-step verification, create an app password (Google Account > Security > App passwords),
host `smtp.gmail.com`, port `587`, user = the address, password = the 16-character app password.
**Outlook / Microsoft 365:** host `smtp-mail.outlook.com` (or `smtp.office365.com`), port `587`, and an app
password if the account has two-step verification; some tenants disable SMTP login, in which case use the webhook.
**Slack:** Apps > Incoming Webhooks > add to a channel > copy the URL.

## Commands (PowerShell, repo folder)

```powershell
# 1. Set the variables for this session only (nothing is written to a file)
$env:ALERT_SMTP_HOST = "smtp.gmail.com"; $env:ALERT_SMTP_PORT = "587"
$env:ALERT_SMTP_USER = "<your address>"; $env:ALERT_SMTP_PASSWORD = "<app password>"
$env:ALERT_EMAIL_FROM = "<your address>"; $env:ALERT_EMAIL_TO = "<your address>"
# 2. A labelled test message through the configured channels
python -m pfe_drai notify --test
# 3. What would be sent for the latest published day; sends nothing, no network
python -m pfe_drai notify --dry-run
```

Global options go before the command (`python -m pfe_drai --lang en ...`), command options after it.

## Never twice

The daily workflow runs `notify` only when its run pushed a new day, **after** the commit, with
`continue-on-error`: a mail problem never fails or delays the record. It then commits
`track_record/alerts/<day>.json`, a list of `{event, channel}` pairs (no address, no URL). A manual re-run of
the workflow, or `notify` by hand, finds that file and skips what was already sent; if one channel failed and
the other did not, only the failed one is retried. `--force` sends again. If the file was never committed
(the step failed after sending), run `notify --dry-run` first and decide before re-sending.

A failed send logs the channel name and the error class and the step (for example `ConnectError`, or `SMTPAuthenticationError at login`), never the message
text, address or URL.

## Privacy

Recipients are not stored in the repository: they are the `ALERT_EMAIL_TO` secret. The recipient list is
read through a `SubscriberSource` (`emails()`); a future accounts feature replaces the environment list with
its own source and nothing else changes. Every message ends with a line saying why it was received and how to stop: until accounts
offer an unsubscribe link, the owner removes the address from the secret (or leaves the Slack channel).

## Settings fingerprint

The `alerts` block sits outside `features`, `regimes`, `models` and `validation`: changing it never changes
the settings fingerprint (`7d25ca34…`) or opens a new backtest record (tested).
