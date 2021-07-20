from typing import Type
from unittest.mock import patch

from django.apps import AppConfig
from django.apps import apps
from django.db.models import Model
from django.test import override_settings
from django.test import TestCase

import csv_permissions.permissions

from .factory import CustomerUserFactory
from .factory import StaffUserFactory
from .models import CustomerProfile
from .models import StaffProfile
from .models import TestModelA
from .models import TestModelD
from .models import TestModelE
from .test_utils import override_csv_permissions

USER1_MODEL = CustomerProfile
USER1_TYPE = CustomerProfile.user_type
USER1_FACTORY = lambda *args, **kwargs: CustomerUserFactory.create(  # noqa: E731
    *args, **kwargs
)  # noqa: E731

USER2_MODEL = StaffProfile
USER2_TYPE = StaffProfile.user_type
USER2_FACTORY = lambda *args, **kwargs: StaffUserFactory.create(*args, **kwargs)  # noqa: E731


def custom_resolve_rule_name(app_config: AppConfig, model: Type[Model], action: str, is_global: bool) -> str:
    app_label = app_config.label.upper()
    model_name = model._meta.object_name
    rule_name = f"{app_label}/{model_name}/{action}/{is_global}"
    return rule_name


@override_settings(CSV_PERMISSIONS_STRICT=True)
class CsvRulesTests(TestCase):
    def test_permissions_parse(self):
        """
        Does not test implementations of individual permissions functions, only that they have been loaded correctly
        from the CSV. yes/no/all have fixed return values, whereas own/custom functions are defined in rules.py.
        """

        csv_data = f"""
        Model,      App,                  Action, Is Global, {USER1_TYPE},  {USER2_TYPE},
        TestModelA, test_csv_permissions, detail, no,        all,           own: model_a,
        TestModelB, test_csv_permissions, change, no,        own,           ,
        TestModelC, test_csv_permissions, detail, no,        all,           all,
        TestModelD, test_csv_permissions, list,   yes,       ,              yes,
        TestModelE, test_csv_permissions, change, no,        own: model_e,  custom: own_model_a_or_model_b,
        """.strip()

        with override_csv_permissions([csv_data]):
            user1 = USER1_FACTORY(email="user2@localhost.test")
            user2 = USER2_FACTORY(email="user1@localhost.test")

            expected_results = (
                # (model, permission, pass_model, has_perm(USER1)?, has_perm(USER2)? )
                (
                    "TestModelA",
                    "test_csv_permissions.detail_testmodela",
                    True,
                    True,
                    True,
                ),
                (
                    "TestModelB",
                    "test_csv_permissions.change_testmodelb",
                    True,
                    True,
                    False,
                ),
                (
                    "TestModelC",
                    "test_csv_permissions.detail_testmodelc",
                    True,
                    True,
                    True,
                ),
                (
                    "TestModelD",
                    "test_csv_permissions.list_testmodeld",
                    False,
                    False,
                    True,
                ),
                (
                    "TestModelE",
                    "test_csv_permissions.change_testmodele",
                    True,
                    True,
                    False,
                ),
            )

            for (
                entity,
                code_name,
                pass_model,
                user1_has_perm,
                user2_has_perm,
            ) in expected_results:
                if pass_model:
                    test_obj = apps.get_model("test_csv_permissions", entity).objects.create()
                else:
                    test_obj = None

                with self.subTest(code_name=code_name, entity=entity):
                    self.assertEqual(
                        user1_has_perm,
                        user1.has_perm(code_name, test_obj),
                        "Unexpected permission mismatch for user1",
                    )

                    self.assertEqual(
                        user2_has_perm,
                        user2.has_perm(code_name, test_obj),
                        "Unexpected permission mismatch for user2",
                    )

    def test_all_global_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,    {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   yes,          all,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaises(RuntimeError):
                user.has_perm("test_csv_permissions.detail_testmodela")

    def test_own_global_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   yes,        own,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaises(RuntimeError):
                user.has_perm("test_csv_permissions.detail_testmodela")

    def test_yes_object_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaises(RuntimeError):
                user.has_perm("test_csv_permissions.detail_testmodela")

    def test_non_existent_permission_error(self):
        """
        Test what happens when permissions aren't present in the file
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         own,
        """.strip()

        with self.assertWarnsRegex(UserWarning, r"No implementation of testmodela_own"):
            user = USER1_FACTORY(email="user@localhost.test")
            with override_csv_permissions([csv_data]):

                with override_settings(CSV_PERMISSIONS_STRICT=False):
                    self.assertEqual(user.has_perm("test_csv_permissions.nonexistentperm_detail"), False)

                with override_settings(CSV_PERMISSIONS_STRICT=True):
                    with self.assertRaises(LookupError):
                        user.has_perm("test_csv_permissions.nonexistentperm_detail")

    def test_empty_file_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaisesMessage(RuntimeError, "Empty permissions file"):
                user.has_perm("test_csv_permissions.detail_testmodelb")

    def test_bad_user_type_error(self):
        """
        Test querying a non-existent user type
        (user type does not exist in the CSV file)
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, approve,  yes,        yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user1 = USER1_FACTORY(email="user1@localhost.test")
            user2 = USER2_FACTORY(email="user2@localhost.test")

            # a user that is recognised should be ok
            self.assertTrue(user1.has_perm("test_csv_permissions.approve_testmodela", None))

            # If user type (group) is not recognised, then just return False
            # This allows it to play nicely with different backends
            # Down the track we might add the option to raise a warning

            with override_settings(CSV_PERMISSIONS_STRICT=True):
                with self.assertRaises(LookupError):
                    user2.has_perm("test_csv_permissions.approve_testmodela", None)

            with override_settings(CSV_PERMISSIONS_STRICT=False):
                self.assertFalse(user2.has_perm("test_csv_permissions.approve_testmodela", None))

    def test_bad_model_type_error(self):
        """
        Test CSV contains a non-existent model type
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelX, test_csv_permissions, approve,  yes,        yes,
        """.strip()

        with self.assertRaises(LookupError):
            with override_csv_permissions([csv_data]):
                user = USER1_FACTORY(email="user@localhost.test")

                # If group is not recognised, then just return False
                # This allows it to play nicely with different backends
                # Down the track we might add the option to raise a warning
                user.has_perm("test_csv_permissions.testmodelx_approve", None)

    @override_settings(CSV_PERMISSIONS_STRICT=False)
    def test_ignored_lines(self):
        """
        Test that commented out lines are ignored
        """
        csv_header_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        """.strip()

        csv_bad_line = "blah blah blah"
        user = USER1_FACTORY(email="user1a@localhost.test")

        with override_csv_permissions([csv_header_data + "\n" * 3 + "#" + csv_bad_line]):
            self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        with self.assertRaises(LookupError):
            with override_csv_permissions([csv_header_data + "\n" * 3 + csv_bad_line]):
                self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        with override_csv_permissions([csv_header_data + "\n" * 3 + "//" + csv_bad_line]):
            self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        pass

    def test_misconfigured_global_permission_error(self):
        """
        Test that a permission which should be object level, raises an error if configured as a global permission.
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   yes,        own,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaisesMessage(
                RuntimeError,
                "Invalid action / global setting",
            ):
                user.has_perm("test_csv_permissions.detail_testmodela")

    def test_misconfigured_object_permission_error(self):
        """
        Test that a permission which should be global level, raises an error if configured as a object permission.
        """
        csv_data = f"""
        Model,      App,                  Action, Is Global,    {USER1_TYPE},
        TestModelA, test_csv_permissions, list,   no,           yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaisesMessage(RuntimeError, "Invalid action / global setting for "):
                user.has_perm("test_csv_permissions.detail_testmodela")

    @patch(
        "csv_permissions.permissions._access_level_all",
        wraps=csv_permissions.permissions._access_level_all,
    )
    def test_all_permission(self, access_level_all_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         all,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            with self.assertRaises(RuntimeError):
                user.has_perm("test_csv_permissions.detail_testmodela", None)

            self.assertEqual(
                1,
                access_level_all_mock.call_count,
                "All function should have been called once",
            )

            test_obj = TestModelA.objects.create()
            self.assertTrue(
                user.has_perm("test_csv_permissions.detail_testmodela", test_obj),
                "User should have access to all objects",
            )

            self.assertEqual(
                2,
                access_level_all_mock.call_count,
                "All function should have been called twice",
            )

    @patch(
        "csv_permissions.permissions._access_level_yes",
        wraps=csv_permissions.permissions._access_level_yes,
    )
    def test_yes_permission(self, access_level_yes_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelD, test_csv_permissions, list,     yes,        yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER2_FACTORY(email="user@localhost.test")

            self.assertTrue(
                user.has_perm("test_csv_permissions.list_testmodeld", None),
                "User should have access with no object",
            )

            self.assertEqual(
                1,
                access_level_yes_mock.call_count,
                "Yes function should have been called once",
            )

            test_obj = TestModelD.objects.create()
            with self.assertRaises(RuntimeError):
                user.has_perm("test_csv_permissions.list_testmodeld", test_obj)

            self.assertEqual(
                2,
                access_level_yes_mock.call_count,
                "Yes function should have been called twice",
            )

    @patch(
        "csv_permissions.permissions._access_level_no",
        wraps=csv_permissions.permissions._access_level_no,
    )
    def test_no_permission(self, access_level_no_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelD, test_csv_permissions, list,     yes,        ,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER1_FACTORY(email="user@localhost.test")

            self.assertFalse(
                user.has_perm("test_csv_permissions.list_testmodeld", None),
                "User should not have access with no object",
            )

            self.assertEqual(
                1,
                access_level_no_mock.call_count,
                "No function should have been called once",
            )

            test_obj = TestModelD.objects.create()
            self.assertFalse(
                user.has_perm("test_csv_permissions.list_testmodeld", test_obj),
                "User should not have access with no object",
            )

            self.assertEqual(
                2,
                access_level_no_mock.call_count,
                "No function should have been called twice",
            )

    @patch(
        "csv_permissions.permissions._access_level_own",
        wraps=csv_permissions.permissions._access_level_own,
    )
    def test_own_permission(self, access_level_own_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         own: model_a,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER2_FACTORY(email="user@localhost.test")

            self.raises = self.assertRaises(RuntimeError)
            with self.raises:
                user.has_perm("test_csv_permissions.detail_testmodela", None)

            self.assertEqual(
                1,
                access_level_own_mock.call_count,
                "Own function should have been called once",
            )

            test_obj = TestModelA.objects.create()
            self.assertTrue(
                user.has_perm("test_csv_permissions.detail_testmodela", test_obj),
                "User should have access to all objects",
            )

            self.assertEqual(
                2,
                access_level_own_mock.call_count,
                "Own function should have been called twice",
            )

    @patch(
        "csv_permissions.permissions._access_level_custom",
        wraps=csv_permissions.permissions._access_level_custom,
    )
    def test_custom_permission(self, access_level_custom_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelE, test_csv_permissions, change,   no,         custom: own_model_a_or_model_b,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = USER2_FACTORY(email="user@localhost.test")

            self.assertFalse(
                user.has_perm("test_csv_permissions.change_testmodele", None),
                "User should not have access with no object",
            )

            self.assertEqual(
                1,
                access_level_custom_mock.call_count,
                "Custom function should have been called once",
            )

            test_obj = TestModelE.objects.create()
            self.assertFalse(
                user.has_perm("test_csv_permissions.change_testmodele", test_obj),
                "User should not have access to a specific object",
            )

            self.assertEqual(
                2,
                access_level_custom_mock.call_count,
                "Custom function should have been called twice",
            )

    @override_settings(CSV_PERMISSIONS_STRICT=False)
    def test_resolve_rule_name(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelE, test_csv_permissions, list,     yes,        yes,
        """.strip()

        user = USER2_FACTORY(email="user@localhost.test")

        with override_csv_permissions([csv_data]):
            # check default permission names
            self.assertTrue(user.has_perm("test_csv_permissions.list_testmodele"))
            self.assertFalse(user.has_perm("test_csv_permissions.list_testmodela"))

            with override_settings(
                CSV_PERMISSIONS_RESOLVE_RULE_NAME=("test_csv_permissions.tests.custom_resolve_rule_name")
            ):
                with override_csv_permissions([csv_data]):

                    # default name should not match anymore
                    self.assertFalse(user.has_perm("test_csv_permissions.list_testmodele"))
                    self.assertFalse(user.has_perm("test_csv_permissions.list_testmodela"))

                    # custom name should match
                    self.assertTrue(user.has_perm("TEST_CSV_PERMISSIONS/TestModelE/list/True"))
                    self.assertFalse(user.has_perm("TEST_CSV_PERMISSIONS/TestModelA/list/True"))

    def test_multiple_csv_files_merge(self):
        csv_data1 = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, view,     no,         all,
        TestModelB, test_csv_permissions, add,      yes,        yes,
        """.strip()

        csv_data2 = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelA, test_csv_permissions, view,     no,         all,
        TestModelC, test_csv_permissions, add,      yes,        yes,
        """.strip()

        csv_data3 = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE}, {USER2_TYPE},
        TestModelD, test_csv_permissions, add,      yes,        yes,          yes,
        """.strip()

        user1 = USER1_FACTORY(email="user1@localhost.test")
        user2 = USER2_FACTORY(email="user2@localhost.test")
        test_a = TestModelA.objects.create()

        with override_csv_permissions([csv_data1, csv_data2, csv_data3]):
            self.assertTrue(user1.has_perm("test_csv_permissions.view_testmodela", test_a))
            self.assertTrue(user2.has_perm("test_csv_permissions.view_testmodela", test_a))

            self.assertTrue(user1.has_perm("test_csv_permissions.add_testmodelb"))
            self.assertFalse(user2.has_perm("test_csv_permissions.add_testmodelb"))

            self.assertFalse(user1.has_perm("test_csv_permissions.add_testmodelc"))
            self.assertTrue(user2.has_perm("test_csv_permissions.add_testmodelc"))

            self.assertTrue(user1.has_perm("test_csv_permissions.add_testmodeld"))
            self.assertTrue(user2.has_perm("test_csv_permissions.add_testmodeld"))

    def test_multiple_csv_files_inconsistent_is_global(self):
        csv_data1 = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,         ,
        """.strip()

        csv_data2 = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelA, test_csv_permissions, foo,      no,        ,
        """.strip()

        user1 = USER1_FACTORY(email="user1@localhost.test")

        with self.assertRaisesRegex(ValueError, 'inconsistent with a previous CSV file'):
            with override_csv_permissions([csv_data1, csv_data2]):
                user1.has_perm("test_csv_permissions.foo_testmodela")

    def test_multiple_csv_files_inconsistent_details(self):
        csv_data1 = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,         yes,
        """.strip()

        csv_data2 = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,        no,
        """.strip()

        user1 = USER1_FACTORY(email="user1@localhost.test")

        # consistent CSV files
        with override_csv_permissions([csv_data1, csv_data1]):
            self.assertTrue(user1.has_perm("test_csv_permissions.foo_testmodela"))

        # inconsistent CSV files
        with self.assertRaisesRegex(ValueError, 'inconsistent with a previous CSV file'):
            with override_csv_permissions([csv_data1, csv_data2]):
                user1.has_perm("test_csv_permissions.foo_testmodela")
