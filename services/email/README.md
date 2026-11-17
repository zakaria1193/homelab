# Email — Resend SMTP credentials

Resend sending-API keys used as the SMTP password for Gmail's own
"Send mail as" feature (Settings → Accounts and Import → Send mail as →
Add another email address), so replying from Gmail as one of these
addresses sends through Resend with the right DKIM/SPF.

SMTP settings are the same for every address below, only the password
differs:

- Server: `smtp.resend.com`
- Port: `465`, SSL
- Username: `resend`
- Password: the matching key in `.env` (git-crypted)

| Domain | Addresses | `.env` variable | Resend key name |
|---|---|---|---|
| sbksocial.com | `contact@`, `support@`, `moderation@` | `RESEND_SMTP_PASSWORD_SBKSOCIAL` | `salsa-social-production` |
| zakariafadli.com | `pro@`, `perso@` | `RESEND_SMTP_PASSWORD_ZAKARIAFADLI` | `zakariafadli-gmail-send-as` |

Both domains' incoming mail goes through Cloudflare Email Routing to
`zakaria1193@gmail.com` first (so Gmail's verification mail for each
"Send mail as" address lands in the same inbox being configured).

sbksocial.com's own app (`salsa-social`) uses the `salsa-social-production`
key too, but as `RESEND_API_KEY` set directly as a Cloudflare Pages secret
on that project — not read from this file. See that repo's
`docs/email.md` for the app side.

Re-adding a "Send mail as" entry (e.g. if one is ever removed or needs
redoing): Gmail → gear icon → **See all settings** → **Accounts and
Import** → **Add another email address** → fill in the address and name →
Next step → fill in the SMTP settings above → **Add Account** → click the
confirmation link Gmail sends to that address (arrives in this same inbox).
