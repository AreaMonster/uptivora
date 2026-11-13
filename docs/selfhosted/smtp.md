# Outgoing email (SMTP)

Uptivora sends every email itself through an SMTP server you choose: outage and recovery
alerts, certificate warnings, invitations, password resets. Without working SMTP, nobody gets
alerted — check it right after installation.

## Settings

| `.env` | Example | Notes |
| --- | --- | --- |
| `UPTIVORA_SMTP_HOST` | `smtp.example.com` | |
| `UPTIVORA_SMTP_PORT` | `587` | 587 with `starttls`, 465 with `tls`, 25 for a local relay |
| `UPTIVORA_SMTP_SECURITY` | `starttls` | `starttls`, `tls` or `none` (only for a relay on your own network) |
| `UPTIVORA_SMTP_USERNAME` | `monitoring@example.com` | Empty if the relay does not need a login |
| `UPTIVORA_SMTP_FROM` | `Uptivora <monitoring@example.com>` | Must be an address the server may send as |

The password goes into `secrets/smtp_password`. After changing anything:

```bash
docker compose up -d
```

## Provider examples

| Provider | Host | Port / security | Username |
| --- | --- | --- | --- |
| Microsoft 365 | `smtp.office365.com` | 587 / starttls | the mailbox address (SMTP AUTH must be enabled for it) |
| Google Workspace | `smtp-relay.gmail.com` or `smtp.gmail.com` | 587 / starttls | the account; use an app password |
| Infomaniak | `mail.infomaniak.com` | 465 / tls | the mailbox address |
| Postfix on the same network | its address | 25 / none | empty |

Any transactional mail service that offers SMTP works the same way.

## Testing

1. Settings → Recipients → **Send test alert** sends a sample alert to you. The list
   *Recent alert emails* below it shows whether it was sent, is being retried, or failed.
2. Admin → System shows the SMTP server in use and the length of the email queue.
3. Every failed attempt is written to Admin → Logs together with the error message from
   your SMTP server.

Failed sends are retried with growing delays for several hours, so a short SMTP outage does
not lose alerts.

## Deliverability

- Add the sending server to your domain's SPF record and sign with DKIM if your provider
  offers it; otherwise alerts may land in spam.
- Alert emails carry a `List-Unsubscribe` header and a one-click link; account emails
  (password reset, invitations) do not and cannot be switched off.
