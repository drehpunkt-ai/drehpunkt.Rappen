"""Swiss dunning levels for ERPNext's Dunning: payment reminder, first and final dunning with letters.

ERPNext keeps fee, interest and letter texts on the Dunning Type. ``create_dunning_types`` sets up the three
usual Swiss levels for a company, with letters in German, French, Italian and English. Fees can only be
charged if the customer agreed to them (e.g. in the general terms), so they are entered when setting up.
"""

import frappe
from frappe import _

# Names of the levels; the print format translates them with the context «Rappen»
LEVELS = ("Payment reminder", "First dunning", "Final dunning")

_GREETING = {
	"de": "<p>Sehr geehrte Damen und Herren</p>",
	"fr": "<p>Madame, Monsieur,</p>",
	"it": "<p>Gentili signore e signori</p>",
	"en": "<p>Dear Sir or Madam</p>",
}
_REGARDS = {
	"de": "<p>Freundliche Grüsse</p>",
	"fr": "<p>Nous vous prions d'agréer nos salutations distinguées.</p>",
	"it": "<p>Distinti saluti</p>",
	"en": "<p>Kind regards</p>",
}
_BODY = {
	"Payment reminder": {
		"de": "Bei der Durchsicht unserer Buchhaltung haben wir festgestellt, dass die folgenden Rechnungen noch offen sind. Vermutlich ist Ihnen die Zahlung entgangen.",
		"fr": "En examinant notre comptabilité, nous avons constaté que les factures suivantes sont encore ouvertes. Le paiement vous a probablement échappé.",
		"it": "Esaminando la nostra contabilità abbiamo constatato che le seguenti fatture sono ancora aperte. Probabilmente il pagamento le è sfuggito.",
		"en": "Going through our accounts, we noticed that the following invoices are still open. The payment has probably slipped your attention.",
	},
	"First dunning": {
		"de": "Trotz unserer Zahlungserinnerung sind die folgenden Rechnungen noch offen.",
		"fr": "Malgré notre rappel de paiement, les factures suivantes sont toujours ouvertes.",
		"it": "Nonostante il nostro promemoria di pagamento, le seguenti fatture sono ancora aperte.",
		"en": "Despite our payment reminder, the following invoices are still open.",
	},
	"Final dunning": {
		"de": "Trotz unserer Zahlungserinnerung und unserer Mahnung sind die folgenden Rechnungen noch immer offen. Dies ist unsere letzte Mahnung.",
		"fr": "Malgré notre rappel de paiement et notre premier rappel, les factures suivantes sont toujours ouvertes. Ceci est notre dernier rappel.",
		"it": "Nonostante il nostro promemoria e il nostro sollecito, le seguenti fatture sono ancora aperte. Questo è il nostro ultimo sollecito.",
		"en": "Despite our payment reminder and our first dunning, the following invoices are still open. This is our final dunning.",
	},
}
_CLOSING = {
	"Payment reminder": {
		"de": "Bitte begleichen Sie den offenen Betrag innert 10 Tagen mit dem beiliegenden Zahlteil. Falls sich Ihre Zahlung mit diesem Schreiben gekreuzt hat, betrachten Sie es bitte als gegenstandslos.",
		"fr": "Nous vous prions de régler le montant dû dans les 10 jours au moyen de la section paiement ci-jointe. Si votre paiement a croisé ce courrier, veuillez ne pas en tenir compte.",
		"it": "La preghiamo di saldare l'importo dovuto entro 10 giorni con la sezione pagamento allegata. Se il pagamento si è incrociato con questa lettera, la consideri priva di oggetto.",
		"en": "Please pay the amount due within 10 days using the enclosed payment part. If your payment has crossed with this letter, please disregard it.",
	},
	"First dunning": {
		"de": "Bitte überweisen Sie den offenen Betrag innert 10 Tagen mit dem beiliegenden Zahlteil.",
		"fr": "Nous vous prions de virer le montant dû dans les 10 jours au moyen de la section paiement ci-jointe.",
		"it": "La preghiamo di versare l'importo dovuto entro 10 giorni con la sezione pagamento allegata.",
		"en": "Please transfer the amount due within 10 days using the enclosed payment part.",
	},
	"Final dunning": {
		"de": "Geht die Zahlung nicht innert 10 Tagen bei uns ein, leiten wir ohne weitere Ankündigung die Betreibung ein.",
		"fr": "Si le paiement ne nous parvient pas dans les 10 jours, nous engagerons une poursuite sans autre avis.",
		"it": "Se il pagamento non ci perviene entro 10 giorni, avvieremo l'esecuzione senza ulteriore preavviso.",
		"en": "If we do not receive the payment within 10 days, we will start debt collection proceedings without further notice.",
	},
}
LANGUAGES = ("de", "fr", "it", "en")


def letter_texts(level: str, default_language: str = "de") -> list[dict]:
	"""Rows for the Dunning Letter Text table of a level, one per language."""
	default = default_language.split("-")[0] if default_language else "de"
	if default not in LANGUAGES:
		default = "de"
	return [
		{
			"language": language,
			"is_default_language": int(language == default),
			"body_text": _GREETING[language] + f"<p>{_BODY[level][language]}</p>",
			"closing_text": f"<p>{_CLOSING[level][language]}</p>" + _REGARDS[language],
		}
		for language in LANGUAGES
		if frappe.db.exists("Language", language)
	]


@frappe.whitelist()
def create_dunning_types(company: str, fees: str | list | None = None, interest: float = 0) -> list[str]:
	"""Create the three Swiss dunning levels for ``company``; existing ones are left as they are.

	``fees`` are the fees of the three levels in the company currency, e.g. ``[0, 20, 30]``.
	"""
	frappe.has_permission("Dunning Type", "create", throw=True)
	fees = frappe.parse_json(fees) if isinstance(fees, str) else fees
	fees = [*(fees or ()), 0, 0, 0]
	values = frappe.get_cached_value(
		"Company", company, ["default_income_account", "cost_center", "default_letter_head"], as_dict=True
	)
	language = frappe.db.get_single_value("System Settings", "language") or "de"
	created = []
	for index, level in enumerate(LEVELS):
		abbr = frappe.get_cached_value("Company", company, "abbr")
		if frappe.db.exists("Dunning Type", f"{level} - {abbr}"):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Dunning Type",
				"dunning_type": level,
				"company": company,
				"dunning_fee": float(fees[index] or 0),
				"rate_of_interest": float(interest or 0),
				"is_default": int(index == 0),
				"income_account": values.default_income_account,
				"cost_center": values.cost_center,
				"dunning_letter_text": letter_texts(level, language),
			}
		).insert()
		created.append(doc.name)
	if created:
		frappe.msgprint(_("Created: {0}").format(", ".join(created)), alert=True)
	return created


def dunning_title(doc) -> str:
	"""Title of a dunning letter: the level without the company suffix, translated for Rappen's levels."""
	level = frappe.db.get_value("Dunning Type", doc.dunning_type, "dunning_type") if doc.dunning_type else ""
	return _(level, context="Rappen") if level in LEVELS else (level or _("Dunning", context="Rappen"))
