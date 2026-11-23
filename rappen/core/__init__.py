"""Swiss payment logic without Frappe.

Everything in this package is plain Python: no imports from frappe or erpnext, no network, no database. The
Frappe layer (doc events, doctypes, print formats) calls into it. This keeps the rules testable with pytest
alone and reusable outside of ERPNext.
"""
