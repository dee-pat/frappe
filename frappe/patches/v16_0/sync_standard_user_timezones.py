import frappe
from frappe.desk.page.setup_wizard.setup_wizard import set_user_timezone

LEGACY_TIME_ZONE = "Asia/Kolkata"


def execute():
	system_timezone = frappe.db.get_single_value("System Settings", "time_zone")
	if not system_timezone:
		return

	for user in frappe.STANDARD_USERS:
		sync_standard_user_timezone(user, system_timezone)


def sync_standard_user_timezone(user, system_timezone):
	user_timezone = frappe.db.get_value("User", user, "time_zone")
	default_timezone = frappe.db.get_value(
		"DefaultValue", {"parent": user, "defkey": "time_zone"}, "defvalue"
	)

	if user_timezone not in (None, LEGACY_TIME_ZONE):
		timezone = user_timezone
	elif default_timezone not in (None, LEGACY_TIME_ZONE):
		timezone = default_timezone
	else:
		timezone = system_timezone

	if timezone == user_timezone == default_timezone:
		return

	set_user_timezone(user, timezone)
