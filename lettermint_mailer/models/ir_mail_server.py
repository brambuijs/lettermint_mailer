import base64
import logging
from email.utils import getaddresses

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

LETTERMINT_SEND_URL = "https://api.lettermint.co/v1/send"
_PRESERVE_HEADERS = ("Message-Id", "In-Reply-To", "References", "Reply-To")


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    # "Lettermint API" as an authentication method (radio, under Gmail OAuth).
    # When selected the Connection tab only shows the Lettermint fields (token + route).
    smtp_authentication = fields.Selection(
        selection_add=[("lettermint", "Lettermint API")],
        ondelete={"lettermint": "set default"},
    )
    lettermint_route = fields.Char(
        string="Lettermint Route",
        help="Optional Lettermint route-slug (selects the sending domain/route).",
    )
    lettermint_test_recipient = fields.Char(
        string="Test Recipient",
        help="Where 'Test Connection' sends a live test mail. Empty = your own "
             "user email. Use a Lettermint test-mailbox to avoid real inboxes.",
    )

    @api.depends("smtp_authentication")
    def _compute_smtp_authentication_info(self):
        lettermint = self.filtered(lambda s: s.smtp_authentication == "lettermint")
        for srv in lettermint:
            srv.smtp_authentication_info = _(
                "Send through the Lettermint HTTP API (HTTPS) instead of SMTP. "
                "Put your Lettermint Sending-token in the Password field below."
            )
        super(IrMailServer, self - lettermint)._compute_smtp_authentication_info()

    # --- helpers --------------------------------------------------------------
    def _is_lettermint(self):
        return bool(self) and self.exists() and self.smtp_authentication == "lettermint"

    def _lettermint_token(self):
        self.ensure_one()
        if not self.smtp_pass:
            raise UserError(_("Lettermint: no Sending-token set (use the Password field)."))
        return self.smtp_pass

    @staticmethod
    def _lm_addrs(header_value):
        if not header_value:
            return []
        return [addr for _n, addr in getaddresses([header_value]) if addr]

    def _send_lettermint(self, message):
        """POST one email.message through the Lettermint HTTP API."""
        self.ensure_one()
        sender = self._lm_addrs(message.get("From"))
        if not sender:
            raise UserError(_("Lettermint: missing From address."))
        to = self._lm_addrs(message.get("To"))
        cc = self._lm_addrs(message.get("Cc"))
        bcc = self._lm_addrs(message.get("Bcc"))
        if not (to or cc or bcc):
            raise UserError(_("Lettermint: no recipients."))

        text_body = html_body = None
        attachments = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                payload = part.get_payload(decode=True) or b""
                attachments.append({
                    "filename": part.get_filename() or "attachment",
                    "content": base64.b64encode(payload).decode(),
                    "content_type": ctype,
                })
            elif ctype == "text/plain" and text_body is None:
                text_body = (part.get_payload(decode=True) or b"").decode(
                    part.get_content_charset() or "utf-8", "replace")
            elif ctype == "text/html" and html_body is None:
                html_body = (part.get_payload(decode=True) or b"").decode(
                    part.get_content_charset() or "utf-8", "replace")

        body = {"from": sender[0], "to": to, "subject": message.get("Subject") or ""}
        if cc:
            body["cc"] = cc
        if bcc:
            body["bcc"] = bcc
        if html_body:
            body["html"] = html_body
        if text_body:
            body["text"] = text_body
        if attachments:
            body["attachments"] = attachments
        if self.lettermint_route:
            body["route"] = self.lettermint_route
        headers = {h: message.get(h) for h in _PRESERVE_HEADERS if message.get(h)}
        if headers:
            body["headers"] = headers

        try:
            resp = requests.post(
                LETTERMINT_SEND_URL,
                json=body,
                headers={"x-lettermint-token": self._lettermint_token()},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(_("Lettermint API request failed: %s") % exc)
        if resp.status_code >= 300:
            raise UserError(_("Lettermint API error %s: %s") % (resp.status_code, resp.text[:300]))

        data = {}
        try:
            data = resp.json()
        except ValueError:
            pass
        msg_id = data.get("message_id") or data.get("id") or message.get("Message-Id") or ""
        _logger.info("Lettermint: sent to=%s cc=%s bcc=%s id=%s", to, cc, bcc, msg_id)
        return msg_id

    # --- overrides ------------------------------------------------------------
    def _connect__(self, *args, **kwargs):
        """Odoo 19 `MailMail.send` opent eerst een SMTP-sessie via `_connect__`
        (vóór `send_email`). Voor een Lettermint-server is er geen SMTP-host →
        de core-connect crasht ('Unable to connect to SMTP Server'). Skip de
        SMTP-connect voor Lettermint-servers: geef None terug (de `send_email`-
        override verstuurt via de HTTP-API en negeert de sessie)."""
        host = kwargs.get("host") or (args[0] if args else None)
        mail_server_id = kwargs.get("mail_server_id")
        server = self.browse()
        if mail_server_id:
            server = self.sudo().browse(mail_server_id).exists()
        elif not host:
            try:
                res = self.sudo()._find_mail_server(kwargs.get("smtp_from"))
                server = (res[0] if isinstance(res, (tuple, list)) else res) or self.browse()
            except Exception:  # noqa: BLE001 — server-selectie mag nooit de send breken
                server = self.browse()
        if server and server._is_lettermint():
            return None
        return super()._connect__(*args, **kwargs)

    def send_email(self, message, mail_server_id=None, smtp_server=None, smtp_port=None,
                   smtp_user=None, smtp_password=None, smtp_encryption=None,
                   smtp_ssl_certificate=None, smtp_ssl_private_key=None,
                   smtp_debug=False, smtp_session=None):
        mail_server = self.browse()
        if mail_server_id:
            mail_server = self.sudo().browse(mail_server_id).exists()
        elif not smtp_server:
            try:
                res = self.sudo()._find_mail_server(email_from=message.get("From"))
                mail_server = (res[0] if isinstance(res, (tuple, list)) else res) or self.browse()
            except Exception:  # noqa: BLE001 - never let server-selection break sending
                mail_server = self.browse()
        if mail_server and mail_server._is_lettermint():
            return mail_server._send_lettermint(message)
        return super().send_email(
            message, mail_server_id=mail_server_id, smtp_server=smtp_server,
            smtp_port=smtp_port, smtp_user=smtp_user, smtp_password=smtp_password,
            smtp_encryption=smtp_encryption, smtp_ssl_certificate=smtp_ssl_certificate,
            smtp_ssl_private_key=smtp_ssl_private_key, smtp_debug=smtp_debug,
            smtp_session=smtp_session)

    def _lettermint_test_message(self):
        """Build the live test mail sent by Test Connection."""
        self.ensure_one()
        from email.message import EmailMessage
        sender = self.smtp_user or self.env.user.email or self.env.user.login
        recipient = self.lettermint_test_recipient or self.env.user.email or self.env.user.login
        if not sender or "@" not in sender:
            raise UserError(_("Lettermint test: no valid From address (set the server's "
                              "Username to a verified sender, or set your user email)."))
        if not recipient or "@" not in recipient:
            raise UserError(_("Lettermint test: no valid recipient (set a Test Recipient "
                              "or your user email)."))
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = _("Lettermint test from Odoo")
        msg.set_content(_("This is a live Lettermint API test message sent by "
                          "'Test Connection' in Odoo. If you received it, outbound works."))
        return msg, recipient

    def test_smtp_connection(self):
        """For Lettermint-API servers: send a LIVE test mail through the API
        (no SMTP socket). Success => green toast; API error => shown."""
        lettermint = self.filtered(lambda s: s.smtp_authentication == "lettermint")
        for srv in lettermint:
            srv._lettermint_token()  # validates the token is present (raises if missing)
            message, recipient = srv._lettermint_test_message()
            msg_id = srv._send_lettermint(message)  # raises UserError on API failure
            _logger.info("Lettermint test-mail sent to=%s id=%s", recipient, msg_id)
        if lettermint:
            recipient = lettermint[0].lettermint_test_recipient or self.env.user.email
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Lettermint API"),
                    "message": _("Test mail sent via Lettermint to %s. Check the inbox / "
                                 "your Lettermint dashboard.") % recipient,
                    "type": "success",
                    "sticky": False,
                },
            }
        return super(IrMailServer, self - lettermint).test_smtp_connection()
