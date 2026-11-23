# Rappen

Swiss localization, built for ERPNext.

Rappen adds what a Swiss company needs to run its books in [ERPNext](https://github.com/frappe/erpnext): QR-bills, bank statements in camt format, payment files in pain.001, the VAT return for the ESTV and dunning with a QR payment part. Everything runs on your own server. Rappen never calls an outside service.

> **Status: early development.** Rappen is not ready for production yet. The list below shows what is done.

## Features

| Area | What Rappen does | Status |
|---|---|---|
| Basics | Checks IBAN (length per country) and QR-IBAN on bank accounts, shows how an address appears on payments (structured address, type S) and warns about what does not fit | done |
| QR-bill | Payment part on invoices, generated locally (error correction M, Swiss cross), QR reference (QRR) with a QR-IBAN, Creditor Reference (SCOR) or none with a regular IBAN, the reference is stored on the invoice | planned |
| Incoming payments | Reads camt.053 and camt.054 into Bank Transactions, matches them to open invoices by reference and books exact matches | planned |
| Dunning | Payment part on ERPNext dunnings, levels with fees and texts in German, French and Italian | planned |
| Outgoing payments | Payment runs from open purchase invoices as pain.001.001.09 (Swiss Payment Standards 2026), checked against the XSD | planned |
| VAT | VAT return from the ledger (effective method and net tax rate) as a report and as eCH-0217 XML for the ESTV ePortal | planned |

Later: eBill, EBICS, payroll.

## Principles

- **Nothing leaves your server.** No external services, no telemetry, no update checks. The QR code is generated in Python on your server, not fetched from a web service.
- **Standards first.** Swiss Implementation Guidelines for the QR-bill (IG 2.3), Swiss Payment Standards 2026 (pain.001.001.09, camt.05x.001.08), eCH-0217 V2.0.0 for the VAT return. Generated files are validated against the official schemas.
- **ERPNext stays ERPNext.** Rappen uses hooks, custom fields and its own doctypes. It does not change ERPNext's code and does not monkey-patch it.
- **Few dependencies.** Only permissively licensed libraries (MIT, BSD, Apache, ISC), pinned to exact versions.

## Compatibility

- ERPNext 16 and Frappe 16, Python 3.14
- Self-hosted (bench or Docker) and Frappe Cloud

## Installation

```sh
bench get-app https://github.com/drehpunkt-ai/drehpunkt.Rappen
bench --site your-site install-app rappen
```

On Frappe Cloud, add the app from GitHub to your bench group and install it on the site.

ERPNext needs to be installed on the site first.

### PDF and Chromium

Frappe 16 renders PDFs with Chromium. If it cannot find Chromium, it downloads it from Google when the first PDF is printed. On a self-hosted server, point Frappe to an installed Chromium to avoid that, for example in a Docker image built with [frappe_docker](https://github.com/frappe/frappe_docker):

```sh
bench set-config -g chromium_path /usr/lib/chromium/chromium-headless-shell
```

## Languages

The user interface is available in English, German, French and Italian.

## Development

The Swiss rules (IBAN, references, addresses, QR-bill, camt, pain.001, eCH-0217) live in `rappen/core` as plain Python without Frappe. Their tests run with pytest alone:

```sh
pip install pytest
pytest
```

Integration tests need a bench with ERPNext and Rappen installed:

```sh
bench --site your-site set-config allow_tests true
bench --site your-site run-tests --app rappen
```

Code style: [ruff](https://docs.astral.sh/ruff/) with the configuration in `pyproject.toml` (tabs, as in Frappe). See [AGENTS.md](AGENTS.md) for the conventions of this repository.

Test data is made up. IBANs and references come from the samples in the SIX implementation guidelines.

## License

[MIT](LICENSE)

ERPNext and Frappe are trademarks of Frappe Technologies Pvt. Ltd. Rappen is an independent project and is not affiliated with or endorsed by Frappe.

Maintained by [Drehpunkt](https://drehpunkt.ai).
