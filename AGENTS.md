# AGENTS.md

Rappen is a Frappe app that adds Swiss localization to ERPNext 16: QR-bill, camt import and reconciliation, pain.001, VAT return (eCH-0217) and dunning. What it does for users is in [README.md](README.md). This file is for whoever changes the code.

The repository will be public under MIT. Write everything as if it already were: no internal names, no customer data, no secrets, no addresses of real people or companies.

## Layout

- `rappen/core/`: the Swiss rules as plain Python. **No imports from frappe or erpnext**, no network, no database. Messages are marked with `_()` from `rappen.core.errors` and raised as `RappenError(message, **params)`. The Frappe layer translates them with `rappen.utils.translate`.
- `rappen/core/tests/`: tests of the core, written as `unittest.TestCase` so that both pytest and `bench run-tests` run them. Golden files go to `rappen/core/tests/data/`.
- `rappen/events/`: handlers for `doc_events` in `hooks.py`, one module per doctype.
- `rappen/custom_fields.py`: every field Rappen adds to doctypes of Frappe and ERPNext. Names start with `rappen_`. `rappen/install.py` creates them on install and migrate and removes them on uninstall. No fixtures for custom fields.
- `rappen/rappen/doctype/`: Rappen's own doctypes (module «Rappen»).
- `rappen/tests/`: integration tests with `frappe.tests.IntegrationTestCase`.
- `rappen/core/schemas/`: official XSD (SIX, eCH), unchanged. eCH imports resolve to the local copies.
- `rappen/qr.py`, `banking.py`, `dunning.py`, `payments.py`, `vat.py`, `accounts.py`: the Frappe side of each feature.
- `rappen/templates/`: payment part and print formats (Jinja).
- `rappen/locale/`: translations (`main.pot`, `de.po`, `fr.po`, `it.po`).

## Rules

- Nothing leaves the server at runtime: no external services, no telemetry, no version checks, no fonts or scripts from CDNs.
- Dependencies only under MIT, BSD, Apache 2.0, ISC or similar, pinned to an exact version in `pyproject.toml`. Check the licenses of transitive dependencies too (LGPL and GPL are out). No dependency on AGPL apps.
- Do not copy code from ERPNext, ERPNextSwiss or other GPL/AGPL apps. Reading them to understand ERPNext is fine.
- Extend ERPNext through hooks, custom fields, doc events and own doctypes. No changes to core files, no monkey patches where a hook exists, no overrides of whole doctype classes.
- Follow the Frappe conventions: structure as created by `bench new-app`, tabs, ruff with the configuration in `pyproject.toml`.
- Follow the standards exactly and name the source in a comment: SIX Implementation Guidelines QR-bill 2.3, Swiss Payment Standards 2026, eCH-0217 V2.0.0. Generated XML is validated against the official XSD, in tests and before every export.

## Language

- Code, identifiers, comments, docs and commit messages in English.
- Every user-facing string goes through `_()` (Python) or `__()` (JavaScript) with the English text as source.
- Translations in `rappen/locale/{de,fr,it}.po`. German in Swiss spelling: «ss», never «ß». Formal address («Sie», «vous»; Italian infinitive for instructions).
- No en or em dashes in user-facing texts.
- Frappe merges the catalogs of all apps, so a msgid that Frappe or ERPNext translate already must not be in Rappen's catalog without context. Generic words in Rappen's own wording get the context «Rappen»: `_("Date", context="Rappen")`, `__("Street", null, "Rappen")`. Labels in doctype JSON cannot have a context; choose a specific wording instead.
- CI fails if a string has no translation in one of the three languages (`.github/scripts/check_translations.py`).

## Tests

- Only made-up test data. IBANs and references from the samples of SIX (QR-IBAN `CH44 3199 9123 0008 8901 2`, IBAN `CH93 0076 2011 6238 5295 7`).
- Core: `pytest` from the repository root.
- Integration: `bench --site <site> run-tests --app rappen`, on a site after the setup wizard for a Swiss company (as in CI). Helpers for test data in `rappen/tests/utils.py`.
- Print layouts: CI uploads the generated PDF as an artifact; the payment part position is also checked in `test_qr_bill.test_pdf`.
- CI (`.github/workflows/ci.yml`): ruff, core tests, integration tests against the pinned ERPNext version and the latest `version-16`, translations.

## Versions

- SemVer. Every release gets an entry in `CHANGELOG.md`.
- GitHub Actions are pinned to a commit SHA, container images to a digest.
