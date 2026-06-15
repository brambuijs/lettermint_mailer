{
    "name": "Lettermint Mailer",
    "version": "1.2.0",
    "summary": "Outbound + inbound email via the Lettermint HTTP API (no SMTP/IMAP).",
    "description": """
Lettermint Mailer
=================
Connects Odoo to Lettermint over HTTPS (443) — no SMTP, no IMAP. Works in
restricted clusters where mail ports are blocked. Outbound and inbound are
independent: enable only outbound, or outbound + inbound.

OUTBOUND (Settings > Technical > Email > Outgoing Mail Servers)
--------------------------------------------------------------
1. Create an Outgoing Mail Server.
2. "Authenticate with" -> **Lettermint API** (radio, under Gmail OAuth).
   The Connection tab then shows only the Lettermint fields (SMTP fields hide).
3. **Password** = your Lettermint project *Sending*-token.
4. **Lettermint Route** (optional) = route-slug to pick the sending domain/route.
5. "Test Connection" validates the token (no SMTP probe).

Sending is transparent: the override is on ir.mail_server.send_email, so Odoo's
normal mail queue (Email Queue Manager cron), templates and notifications all go
through Lettermint. Retries/state are standard Odoo.

INBOUND (Settings > Technical > Email > Incoming Mail Servers)
-------------------------------------------------------------
1. Create an Incoming Mail Server, Server Type -> **Lettermint API (webhook)**.
2. Copy the shown **Webhook URL** (https://<your-odoo>/lettermint/inbound) into
   your Lettermint inbound-route.
3. Paste the route's **Signing-secret** (whsec_...) into the secret field, Save,
   "Test & Confirm".
   Having such a server = inbound ON. Remove it = inbound OFF (webhooks rejected).
   Multiple servers/secrets supported (one per inbound-route/domain).

Inbound is push (webhook), not polling. Lettermint POSTs each mail (HMAC-signed,
"t=,v1=" header); the controller verifies the signature, fetches the raw message
(raw.url / inline raw.content) and hands it to Odoo's mail-gateway
(mail.thread.message_process, model=False).

ALIASES / routing (Settings > Technical > Email > Aliases)
----------------------------------------------------------
Routing uses Odoo's native aliases — exactly like a catch-all setup:
* Set an Alias Domain (Settings > General, e.g. bb-open.com).
* Create aliases: ``sales`` -> CRM Lead, ``info`` -> Helpdesk Ticket, ``jobs``
  -> Recruitment, etc. (Alias -> target model).
* Mail to an aliased address creates/updates the right record.
* Customer **replies** (In-Reply-To/References) land back in the originating
  record's chatter automatically — no new record.
* Mail matching no alias and no existing thread has no route: accepted and
  dropped (only aliased/threaded mail is ingested), so no retry-storm.

A system parameter ``lettermint.webhook_secret`` is accepted as a fallback
signing-secret (handy for testing) in addition to the Incoming-server secrets.

Modelled on the Postmark/Sendgrid Odoo connectors.
""",
    "author": "BB Open Solutions",
    "website": "https://bb-open.com",
    "license": "LGPL-3",
    "category": "Technical",
    "depends": ["mail"],
    "data": ["views/ir_mail_server_views.xml"],
    "external_dependencies": {"python": ["requests"]},
    "installable": True,
    "application": False,
}
