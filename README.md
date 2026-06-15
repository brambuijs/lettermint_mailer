# Lettermint Mailer (Odoo)

Odoo-module van **BB Open Solutions** voor uitgaande én inkomende e-mail via de
**[Lettermint](https://lettermint.co) HTTP-API** — geen SMTP/IMAP nodig.

- **Uitgaand**: `ir.mail_server` verstuurt via de Lettermint REST-API (Bearer-token)
  i.p.v. SMTP. Handig in omgevingen waar poort 25/465/587 dichtstaat.
- **Inkomend**: een webhook-controller ontvangt Lettermint-inbound en levert af op
  de juiste Odoo-aliassen (catch-all/alias-routing), zonder IMAP-fetchmail.
- **Test Connection**-knop op de mailserver-config (live API-check).

## Versies / branches
- **`main`** → Odoo **19.0** (v1.2.1)
- **`18.0`** → Odoo **18.0** (v1.2.0)

## Installatie
- Odoo 18.0 / 19.0 (kies de juiste branch)
- Afhankelijkheden: `mail` (core) + Python `requests`
- Plaats `lettermint_mailer/` in je addons-path → installeren → configureer de
  Lettermint-API-token op de outgoing mail server + de inbound-webhook-route.

## Licentie
LGPL-3. © BB Open Solutions — https://bb-open.com

> Gedeeld voor integratie-/review-doeleinden. Issues/PR's welkom.
