import base64
import hashlib
import hmac
import json
import logging
import urllib.request

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# System parameter holding the Lettermint inbound webhook signing-secret.
WEBHOOK_SECRET_PARAM = "lettermint.webhook_secret"


class LettermintInbound(http.Controller):
    """Receive Lettermint inbound webhooks and hand the raw mail to Odoo's
    mail-gateway (mail.thread.message_process). model=False → Odoo routes on
    the recipient alias (sales@ -> crm.lead, info@ -> helpdesk, ...).
    """

    def _secrets(self):
        """Signing-secrets that enable inbound. Sourced from the Lettermint
        Incoming-Mail-Servers (server_type='lettermint'); no such server =>
        inbound is OFF (empty list => every webhook rejected). A system
        parameter is accepted as a fallback (e.g. testing)."""
        env = request.env
        servers = env["fetchmail.server"].sudo().search([
            ("server_type", "=", "lettermint"),
            ("lettermint_webhook_secret", "!=", False),
        ])
        secrets = list(servers.mapped("lettermint_webhook_secret"))
        param = env["ir.config_parameter"].sudo().get_param(WEBHOOK_SECRET_PARAM)
        if param:
            secrets.append(param)
        return [s for s in secrets if s]

    def _verify(self, sig_header, body):
        secrets = self._secrets()
        if not secrets or not sig_header:
            return False
        # Stripe-style header: "t=<ts>,v1=<hmac_hex>"; HMAC-SHA256 over "<ts>.<body>".
        parts = {}
        for p in sig_header.split(","):
            if "=" in p:
                k, v = p.split("=", 1)
                parts[k.strip()] = v.strip()
        ts, v1 = parts.get("t"), parts.get("v1")
        if not ts or not v1:
            return False
        signed = ts.encode() + b"." + body
        for secret in secrets:
            expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, v1):
                return True
        return False

    @staticmethod
    def _extract_raw_eml(ev):
        """Get the raw RFC822 bytes from the webhook body. Lettermint sends a
        signed URL (raw.url); we also accept inline raw.content (base64) or a
        raw string so the endpoint is testable without a live signed URL."""
        msg = ev
        for k in ("data", "payload", "message", "inbound"):
            if isinstance(ev.get(k), dict):
                msg = ev[k]
                break
        raw = msg.get("raw") or ev.get("raw")
        if isinstance(raw, dict):
            if raw.get("url"):
                with urllib.request.urlopen(raw["url"], timeout=30) as r:
                    return r.read()
            if raw.get("content"):
                return base64.b64decode(raw["content"])
        if isinstance(raw, str) and raw:
            try:
                return base64.b64decode(raw, validate=True)
            except Exception:  # noqa: BLE001 - not base64 -> treat as literal MIME
                return raw.encode()
        return None

    @http.route("/lettermint/inbound", type="http", auth="public",
                methods=["POST"], csrf=False, save_session=False)
    def inbound(self, **kw):
        body = request.httprequest.get_data()
        if not self._verify(request.httprequest.headers.get("X-Lettermint-Signature"), body):
            _logger.warning("Lettermint inbound: invalid signature")
            return request.make_response("bad signature", status=401)
        try:
            ev = json.loads(body)
        except ValueError:
            return request.make_response("bad json", status=400)
        try:
            raw_eml = self._extract_raw_eml(ev)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Lettermint inbound: raw fetch failed: %s", exc)
            return request.make_response("raw fetch failed", status=502)
        if not raw_eml:
            _logger.warning("Lettermint inbound: no raw mail (keys=%s)", list(ev.keys()))
            return request.make_response("no raw", status=422)
        # model=False -> Odoo routes on the recipient alias OR (for replies)
        # on the In-Reply-To/References thread, so customer replies land back
        # in the originating record's chatter. Mail matching neither an alias
        # nor a known thread has no route: accept + drop (catchall semantics),
        # do not 500 (avoids a Lettermint retry-storm on non-aliased recipients).
        try:
            res = request.env["mail.thread"].sudo().message_process(
                False, raw_eml, save_original=True)
            _logger.info("Lettermint inbound: processed res=%s size=%s", res, len(raw_eml))
            return request.make_response("ok", status=200)
        except ValueError as exc:
            _logger.info("Lettermint inbound: no alias/thread route, dropped (%s)", exc)
            return request.make_response("no route, ignored", status=200)
        except Exception as exc:  # noqa: BLE001 - unexpected -> 500 so Lettermint retries
            _logger.exception("Lettermint inbound: message_process failed: %s", exc)
            return request.make_response("processing error", status=500)
