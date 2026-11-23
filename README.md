# Rappen

Swiss localization, built for ERPNext.

Rappen adds what a Swiss company needs to run its books in [ERPNext](https://github.com/frappe/erpnext): QR-bills, bank statements in camt format, payment files in pain.001, the VAT return for the ESTV and dunning with a QR payment part. Everything runs on your own server. Rappen never calls an outside service.

> **Status: early development.** All features of the first version are in place and tested in CI, but Rappen has not run in production yet.

## Features

| Area | What Rappen does |
|---|---|
| Basics | Checks IBAN (length per country) and QR-IBAN on bank accounts, shows how an address appears on payments (structured address, type S) and completes ERPNext's Swiss chart of accounts, which lacks the account types for receivables, payables, revenue and VAT |
| QR-bill | Payment part with receipt on invoices and dunnings, generated locally (error correction M, Swiss cross), QR reference (QRR) with a QR-IBAN, Creditor Reference (SCOR) with a regular IBAN, Swico billing information, texts in German, French, Italian and English |
| Incoming payments | Reads camt.053 and camt.054 (versions 001.04 to 001.08) into Bank Transactions, splits batch entries, skips what was imported before, links payments to invoices and dunnings by reference and books exact matches |
| Dunning | Three Swiss dunning levels with letters in four languages and the fees you enter; a payment on the dunning settles invoices and fee |
| Outgoing payments | Reads the supplier's QR-bill from a hand scanner, collects due purchase invoices in a payment proposal and writes pain.001.001.09 after the Swiss Payment Standards 2026 (QR-IBAN, IBAN, SEPA), checked against the Swiss schema; debits in the statement are matched by end-to-end ID |
| VAT | VAT return for the effective and the net tax rate method, calculated from the books, editable, as eCH-0217 V2.0.0 XML for the ESTV ePortal, checked against the schema |

Later: eBill, EBICS, payroll, foreign payments outside SEPA.

## Getting started

1. Install Rappen (see below). Companies in Switzerland set up with the Swiss chart of accounts get their missing account types and default accounts after the setup wizard. For an existing company, use **Rappen Settings > Complete Swiss chart of accounts**.
2. Enter the IBAN and, if you have one, the QR-IBAN on your company bank account. Mark it as default.
3. Print invoices with the print format **Sales Invoice QR-bill**, dunnings with **Dunning QR-bill**.
4. Create the dunning levels with **Rappen Settings > Create Swiss dunning levels**.
5. Import bank statements with **CAMT Import**, pay suppliers with **Payment Proposal**, file the VAT return with **VAT Return**.

### The payment part in your own print formats

`{{ rappen_payment_part(doc) }}` adds the payment part on a page of its own. The guidelines require it at the bottom edge of the paper, so the print format needs zero page margins. Frappe takes them from this rule:

```css
.print-format { margin-top: 0; margin-bottom: 0; margin-left: 0; margin-right: 0; }
```

Rappen's print formats do this and give the letter its own margins. Alternatively, `{{ rappen_payment_part(doc, page=False) }}` returns just the 210 x 105 mm block to place yourself.

### camt files from other systems

A CAMT Import can be created through Frappe's REST API, e.g. from a workflow that fetches statements: upload the file, create the CAMT Import with it and call its method `run_import`.

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

The CI runs the setup wizard (Switzerland, CHF, Swiss chart of accounts) before the integration tests; do the same on a development site.

## Schemas

Generated files are validated against the official schemas, which Rappen ships unchanged in `rappen/core/schemas`: the Swiss version of pain.001.001.09 by SIX (with its copyright notice) and eCH-0217 V2.0.0 with the eCH schemas it imports, from www.ech.ch. They are used for validation only.

## License

[MIT](LICENSE)

ERPNext and Frappe are trademarks of Frappe Technologies Pvt. Ltd. Rappen is an independent project and is not affiliated with or endorsed by Frappe.

Maintained by [Drehpunkt](https://drehpunkt.ai).
