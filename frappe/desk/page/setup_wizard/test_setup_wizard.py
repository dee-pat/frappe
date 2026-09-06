# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
from unittest.mock import MagicMock, patch

import frappe
import frappe.defaults
from frappe.desk.page.setup_wizard import setup_wizard
from frappe.patches.v16_0.sync_standard_user_timezones import sync_standard_user_timezone
from frappe.tests import IntegrationTestCase, UnitTestCase, set_user
from frappe.utils.synchronization import LockTimeoutError


def fake_hooks(apps):
	def get_hooks(hook=None, default=None, app_name=None):
		if app_name:
			return apps.get(app_name, {})
		merged = []
		for app_hooks in apps.values():
			merged += app_hooks.get(hook, [])
		return merged

	return get_hooks


class TestSetupWizardUrl(UnitTestCase):
	def resolve(self, apps):
		with (
			patch.object(frappe, "get_installed_apps", return_value=list(apps)),
			patch.object(frappe, "get_active_apps", return_value=list(apps)),
			patch.object(frappe, "get_hooks", side_effect=fake_hooks(apps)),
		):
			url = setup_wizard.get_setup_wizard_url()
			builtin = setup_wizard.site_requires_builtin_wizard()
			return url, builtin

	def test_defaults_to_desk(self):
		url, builtin = self.resolve({"frappe": {}})
		self.assertEqual(url, "/desk/setup-wizard")
		self.assertFalse(builtin)

	def test_uses_app_url(self):
		url, builtin = self.resolve({"suite": {"setup_wizard_url": ["/suite/setup"]}})
		self.assertEqual(url, "/suite/setup")
		self.assertFalse(builtin)

	def test_last_app_wins(self):
		url, _ = self.resolve(
			{
				"suite": {"setup_wizard_url": ["/suite/setup"]},
				"gameplan": {"setup_wizard_url": ["/gameplan/setup"]},
			}
		)
		self.assertEqual(url, "/gameplan/setup")

	def test_stage_app_forces_desk(self):
		url, builtin = self.resolve(
			{
				"suite": {"setup_wizard_url": ["/suite/setup"]},
				"erpnext": {"setup_wizard_stages": ["erpnext.setup.get_setup_stages"]},
			}
		)
		self.assertEqual(url, "/desk/setup-wizard")
		self.assertTrue(builtin)

	def test_complete_hook_forces_desk(self):
		url, builtin = self.resolve(
			{
				"suite": {"setup_wizard_url": ["/suite/setup"]},
				"crm": {"setup_wizard_complete": ["crm.setup.after_complete"]},
			}
		)
		self.assertEqual(url, "/desk/setup-wizard")
		self.assertTrue(builtin)


class TestCompleteAppSetup(IntegrationTestCase):
	def test_needs_system_manager(self):
		with set_user("Guest"):
			self.assertRaises(frappe.PermissionError, setup_wizard.complete_app_setup)

	def test_refuses_builtin_site(self):
		with patch.object(setup_wizard, "site_requires_builtin_wizard", return_value=True):
			self.assertRaises(frappe.ValidationError, setup_wizard.complete_app_setup)

	def test_skips_when_already_complete(self):
		with (
			patch.object(setup_wizard, "site_requires_builtin_wizard", return_value=False),
			patch.object(frappe, "is_setup_complete", return_value=True),
			patch.object(setup_wizard, "process_setup_stages") as process_stages,
		):
			self.assertEqual(setup_wizard.complete_app_setup(), {"status": "ok"})
			process_stages.assert_not_called()

	def test_lock_timeout_never_reports_false_success(self):
		lock = MagicMock()
		lock.__enter__.side_effect = LockTimeoutError
		with (
			patch.object(setup_wizard, "site_requires_builtin_wizard", return_value=False),
			patch.object(setup_wizard, "filelock", return_value=lock),
		):
			with patch.object(frappe, "is_setup_complete", return_value=False):
				self.assertRaises(frappe.ValidationError, setup_wizard.complete_app_setup)
			with patch.object(frappe, "is_setup_complete", return_value=True):
				self.assertEqual(setup_wizard.complete_app_setup(), {"status": "ok"})


class TestStandardUserTimezone(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.original_user_timezones = {
			user: frappe.db.get_value("User", user, "time_zone") for user in frappe.STANDARD_USERS
		}
		self.original_defaults = {
			user: frappe.db.get_value("DefaultValue", {"parent": user, "defkey": "time_zone"}, "defvalue")
			for user in frappe.STANDARD_USERS
		}
		self.addCleanup(self.restore_standard_user_timezones)

	def restore_standard_user_timezones(self):
		for user in frappe.STANDARD_USERS:
			frappe.db.set_value(
				"User", user, "time_zone", self.original_user_timezones[user], update_modified=False
			)
			if self.original_defaults[user] is None:
				frappe.defaults.clear_default("time_zone", parent=user)
			else:
				frappe.defaults.set_default("time_zone", self.original_defaults[user], user)

	def test_set_timezone_updates_standard_user_defaults(self):
		old_timezone = "Asia/Kolkata"
		new_timezone = "Africa/Nairobi"

		for user in frappe.STANDARD_USERS:
			frappe.db.set_value("User", user, "time_zone", old_timezone, update_modified=False)
			frappe.defaults.set_default("time_zone", old_timezone, user)

		setup_wizard.set_timezone(new_timezone)

		for user in frappe.STANDARD_USERS:
			self.assertEqual(frappe.db.get_value("User", user, "time_zone"), new_timezone)
			self.assertEqual(frappe.defaults.get_user_default("time_zone", user), new_timezone)

	def test_update_global_settings_syncs_timezone_inline(self):
		args = frappe._dict(language="English", timezone="Africa/Nairobi")

		with (
			patch.object(setup_wizard, "update_system_settings"),
			patch.object(setup_wizard, "create_or_update_user"),
			patch.object(setup_wizard, "set_timezone") as set_timezone,
		):
			setup_wizard.update_global_settings(args)

		set_timezone.assert_called_once_with("Africa/Nairobi")

	def test_initialize_system_settings_syncs_standard_users(self):
		system_settings = frappe._dict(setup_complete=0, time_zone="Africa/Nairobi")
		system_settings.save = lambda: None

		with (
			patch.object(frappe, "get_single", return_value=system_settings),
			patch.object(setup_wizard, "create_or_update_user"),
			patch.object(setup_wizard, "set_timezone") as set_timezone,
		):
			setup_wizard.initialize_system_settings_and_user(
				{
					"language": "English",
					"country": "Kenya",
					"currency": "KES",
					"time_zone": "Africa/Nairobi",
				},
				{"email": "test@example.com"},
			)

		set_timezone.assert_called_once_with("Africa/Nairobi")

	def test_timezone_patch_repairs_defaults_and_preserves_overrides(self):
		user = "Administrator"
		for user_timezone, default_timezone, expected in (
			("Asia/Kolkata", "Asia/Kolkata", "Africa/Nairobi"),
			("America/New_York", "Asia/Kolkata", "America/New_York"),
			("", "Asia/Kolkata", "Africa/Nairobi"),
			(None, "", "Africa/Nairobi"),
			("", "America/New_York", "America/New_York"),
		):
			with self.subTest(user_timezone=user_timezone, default_timezone=default_timezone):
				frappe.db.set_value("User", user, "time_zone", user_timezone, update_modified=False)
				frappe.defaults.set_default("time_zone", default_timezone, user)

				sync_standard_user_timezone(user, "Africa/Nairobi")
				sync_standard_user_timezone(user, "Africa/Nairobi")

				self.assertEqual(frappe.db.get_value("User", user, "time_zone"), expected)
				self.assertEqual(frappe.defaults.get_user_default("time_zone", user), expected)
