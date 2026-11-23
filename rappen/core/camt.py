"""Read bank statements and notifications in ISO 20022 camt format.

Supported: camt.053 (statement), camt.054 (debit/credit notification) and camt.052 (intraday report), versions
001.04 to 001.08, as delivered by Swiss banks under the Swiss Payment Standards. From 14 November 2026 the
banks send version 001.08; older versions are read as long as banks still deliver them.

Only booked entries are read. A batch entry (e.g. all QR payments of a day) is split into its transactions if
the file contains their details; otherwise it is returned as one transaction marked ``batch``, and the details
can come later in a camt.054. The parser uses the standard library only and never loads external entities.
"""

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from rappen.core import reference as references
from rappen.core.errors import RappenError, _

KINDS = {"BkToCstmrStmt": "camt.053", "BkToCstmrDbtCdtNtfctn": "camt.054", "BkToCstmrAcctRpt": "camt.052"}
CONTAINERS = {"camt.053": "Stmt", "camt.054": "Ntfctn", "camt.052": "Rpt"}
NOT_PROVIDED = "NOTPROVIDED"
MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Transaction:
	"""One movement on the account, as it becomes a Bank Transaction in ERPNext."""

	transaction_id: str
	entry_reference: str
	booking_date: date
	value_date: date | None
	amount: Decimal
	currency: str
	credit: bool
	reference: str = ""
	reference_type: str = references.NON
	end_to_end_id: str = ""
	party_name: str = ""
	party_iban: str = ""
	message: str = ""
	bank_transaction_code: str = ""
	charges: Decimal = Decimal(0)
	reversal: bool = False
	batch: bool = False
	batch_count: int = 0


@dataclass
class Statement:
	"""One statement (camt.053), notification (camt.054) or report (camt.052) of one account."""

	kind: str
	version: str
	message_id: str
	statement_id: str
	account_iban: str
	currency: str
	from_date: date | None = None
	to_date: date | None = None
	opening_balance: Decimal | None = None
	closing_balance: Decimal | None = None
	transactions: list[Transaction] = field(default_factory=list)


def parse(data: bytes) -> list[Statement]:
	"""All statements in a camt file. Raises ``RappenError`` if the file is not a camt file Rappen can read."""
	if len(data) > MAX_BYTES:
		raise RappenError(_("The file is larger than 50 MB."))
	if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data[:4096]:
		raise RappenError(_("The file contains a document type declaration, which camt files never have."))
	try:
		root = ET.fromstring(data)
	except ET.ParseError as error:
		raise RappenError(_("The file is not valid XML: {error}"), error=str(error))

	namespace = _namespace(root)
	match = re.fullmatch(r"urn:iso:std:iso:20022:tech:xsd:(camt\.05[234])\.(001\.0[4-8])", namespace)
	if not match:
		raise RappenError(
			_("This is not a camt.052, camt.053 or camt.054 file in version 001.04 to 001.08 ({namespace})."),
			namespace=namespace or "-",
		)
	kind, version = match.groups()
	document = root[0] if len(root) else None
	if document is None or _local(document.tag) not in KINDS or KINDS[_local(document.tag)] != kind:
		raise RappenError(_("The file does not contain a bank statement or notification."))

	message_id = _text(document, "GrpHdr/MsgId")
	statements = []
	for container in document.findall("{*}" + CONTAINERS[kind]):
		statements.append(_statement(container, kind, version, message_id))
	return statements


def _statement(container: ET.Element, kind: str, version: str, message_id: str) -> Statement:
	statement_id = _text(container, "Id")
	iban = _text(container, "Acct/Id/IBAN")
	if not iban:
		raise RappenError(_("Statement {id} has no IBAN for the account."), id=statement_id)
	statement = Statement(
		kind=kind,
		version=version,
		message_id=message_id,
		statement_id=statement_id,
		account_iban=iban.replace(" ", "").upper(),
		currency=_text(container, "Acct/Ccy"),
		from_date=_date(_text(container, "FrToDt/FrDtTm")),
		to_date=_date(_text(container, "FrToDt/ToDtTm")),
	)
	for balance in container.findall("{*}Bal"):
		code = _text(balance, "Tp/CdOrPrtry/Cd")
		amount = _signed(balance)
		if code in ("OPBD", "PRCD") and statement.opening_balance is None:
			statement.opening_balance = amount
		elif code == "CLBD":
			statement.closing_balance = amount

	for index, entry in enumerate(container.findall("{*}Ntry"), start=1):
		if not _booked(entry):
			continue
		statement.transactions += _transactions(entry, statement, index)
	return statement


def _transactions(entry: ET.Element, statement: Statement, index: int) -> list[Transaction]:
	entry_amount = _amount(entry, "Amt")
	currency = _attr(entry, "Amt", "Ccy") or statement.currency
	credit = _text(entry, "CdtDbtInd") == "CRDT"
	entry_reference = (
		_text(entry, "AcctSvcrRef")
		or _text(entry, "NtryRef")
		or _fallback_id(
			statement, index, entry_amount, _text(entry, "BookgDt/Dt") or _text(entry, "BookgDt/DtTm")
		)
	)
	common = {
		"entry_reference": entry_reference,
		"booking_date": _date(_text(entry, "BookgDt/Dt") or _text(entry, "BookgDt/DtTm")),
		"value_date": _date(_text(entry, "ValDt/Dt") or _text(entry, "ValDt/DtTm")),
		"currency": currency,
		"bank_transaction_code": _bank_transaction_code(entry),
		"reversal": _text(entry, "RvslInd").lower() == "true",
	}
	if common["booking_date"] is None:
		raise RappenError(_("Entry {reference} has no booking date."), reference=entry_reference)

	details = [tx for block in entry.findall("{*}NtryDtls") for tx in block.findall("{*}TxDtls")]
	batch_count = int(_text(entry, "NtryDtls/Btch/NbOfTxs") or 0)
	entry_message = _text(entry, "AddtlNtryInf")

	if not details:
		return [
			Transaction(
				transaction_id=entry_reference,
				amount=entry_amount,
				credit=credit,
				message=entry_message,
				charges=_charges(entry),
				batch=batch_count > 1,
				batch_count=batch_count,
				**common,
			)
		]

	transactions = []
	for number, detail in enumerate(details, start=1):
		amount = _amount(detail, "Amt") or _amount(detail, "AmtDtls/TxAmt/Amt")
		if amount is None:
			amount = entry_amount if len(details) == 1 else None
		if amount is None:
			raise RappenError(
				_("A transaction of entry {reference} has no amount."), reference=entry_reference
			)
		detail_credit = _text(detail, "CdtDbtInd") or ("CRDT" if credit else "DBIT")
		ref, ref_type = _structured_reference(detail)
		party = "Dbtr" if detail_credit == "CRDT" else "Cdtr"
		end_to_end = _text(detail, "Refs/EndToEndId")
		message = " ".join(
			part
			for part in (
				" ".join(element.text or "" for element in detail.findall("{*}RmtInf/{*}Ustrd")).strip(),
				_text(detail, "AddtlTxInf"),
			)
			if part
		)
		transactions.append(
			Transaction(
				transaction_id=_text(detail, "Refs/AcctSvcrRef") or f"{entry_reference}/{number}",
				amount=amount,
				credit=detail_credit == "CRDT",
				reference=ref,
				reference_type=ref_type,
				end_to_end_id="" if end_to_end == NOT_PROVIDED else end_to_end,
				party_name=_party_name(detail, party),
				party_iban=_text(detail, f"RltdPties/{party}Acct/Id/IBAN").replace(" ", "").upper(),
				message=message or entry_message,
				charges=_charges(detail),
				**common,
			)
		)
	return transactions


def _structured_reference(detail: ET.Element) -> tuple[str, str]:
	"""QR reference or Creditor Reference of a transaction, if it has a valid one."""
	for info in detail.findall("{*}RmtInf/{*}Strd/{*}CdtrRefInf"):
		value = references.compact(_text(info, "Ref"))
		if not value:
			continue
		try:
			kind = references.reference_type(value)
		except RappenError:
			continue
		if kind != references.NON:
			return value, kind
	return "", references.NON


def _party_name(detail: ET.Element, party: str) -> str:
	# Version 001.04 has Dbtr/Nm, later versions Dbtr/Pty/Nm
	return _text(detail, f"RltdPties/{party}/Pty/Nm") or _text(detail, f"RltdPties/{party}/Nm")


def _charges(element: ET.Element) -> Decimal:
	"""Charges the bank deducted from the amount (ChrgInclInd true)."""
	total = Decimal(0)
	for record in element.findall("{*}Chrgs/{*}Rcrd"):
		if _text(record, "ChrgInclInd").lower() == "true":
			total += _amount(record, "Amt") or Decimal(0)
	return total


def _bank_transaction_code(entry: ET.Element) -> str:
	parts = [
		_text(entry, path) for path in ("BkTxCd/Domn/Cd", "BkTxCd/Domn/Fmly/Cd", "BkTxCd/Domn/Fmly/SubFmlyCd")
	]
	return "/".join(part for part in parts if part)


def _booked(entry: ET.Element) -> bool:
	# 001.04: <Sts>BOOK</Sts>, from 001.08: <Sts><Cd>BOOK</Cd></Sts>
	return (_text(entry, "Sts/Cd") or _text(entry, "Sts")) == "BOOK"


def _fallback_id(statement: Statement, index: int, amount, booked: str) -> str:
	key = f"{statement.account_iban}|{statement.statement_id}|{index}|{amount}|{booked}"
	return "RAPPEN-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _signed(balance: ET.Element) -> Decimal | None:
	amount = _amount(balance, "Amt")
	if amount is None:
		return None
	return -amount if _text(balance, "CdtDbtInd") == "DBIT" else amount


def _namespace(element: ET.Element) -> str:
	return element.tag[1:].split("}", 1)[0] if element.tag.startswith("{") else ""


def _local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1]


def _path(path: str) -> str:
	return "/".join("{*}" + part for part in path.split("/"))


def _text(element: ET.Element, path: str) -> str:
	found = element.find(_path(path))
	return (found.text or "").strip() if found is not None else ""


def _attr(element: ET.Element, path: str, name: str) -> str:
	found = element.find(_path(path))
	return found.get(name, "") if found is not None else ""


def _amount(element: ET.Element, path: str) -> Decimal | None:
	value = _text(element, path)
	if not value:
		return None
	try:
		return Decimal(value)
	except InvalidOperation:
		raise RappenError(_("{value} is not a valid amount."), value=value)


def _date(value: str) -> date | None:
	if not value:
		return None
	try:
		return date.fromisoformat(value[:10])
	except ValueError:
		raise RappenError(_("{value} is not a valid date."), value=value)
