from odoo import api, fields, models, _


class FetchmailServer(models.Model):
    """Incoming side: a 'Lettermint API (webhook)' server-type. It is a
    config-holder, not a poller — Lettermint pushes mail to the webhook URL.
    The record stores the inbound-route signing-secret (the controller verifies
    the HMAC against all such records) and shows the URL to paste into Lettermint.
    """
    _inherit = "fetchmail.server"

    server_type = fields.Selection(
        selection_add=[("lettermint", "Lettermint API (webhook)")],
        ondelete={"lettermint": "set default"},
    )
    lettermint_webhook_secret = fields.Char(
        string="Webhook Signing-secret",
        help="The Lettermint inbound-route signing-secret (whsec_...). "
             "Incoming webhooks are HMAC-verified against this.",
    )
    lettermint_webhook_url = fields.Char(
        string="Webhook URL",
        compute="_compute_lettermint_webhook_url",
        help="Paste this URL into your Lettermint inbound-route.",
    )

    def _compute_lettermint_webhook_url(self):
        base = (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")
        for srv in self:
            srv.lettermint_webhook_url = base + "/lettermint/inbound"

    @api.depends("server_type")
    def _compute_server_type_info(self):
        lm = self.filtered(lambda s: s.server_type == "lettermint")
        for srv in lm:
            srv.server_type_info = _(
                "Lettermint pushes inbound mail to the webhook URL below — no polling. "
                "Paste the URL into your Lettermint inbound-route and store the route's "
                "signing-secret here. Routing (sales@, info@, ...) uses Odoo aliases."
            )
        super(FetchmailServer, self - lm)._compute_server_type_info()

    def button_confirm_login(self):
        # No IMAP/POP socket for Lettermint — just mark confirmed.
        lm = self.filtered(lambda s: s.server_type == "lettermint")
        lm.write({"state": "done"})
        other = self - lm
        if other:
            return super(FetchmailServer, other).button_confirm_login()
        return True

    def fetch_mail(self):
        # Lettermint is push (webhook) — nothing to poll.
        other = self.filtered(lambda s: s.server_type != "lettermint")
        if other:
            return super(FetchmailServer, other).fetch_mail()
        return True
