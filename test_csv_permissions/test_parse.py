from typing import Type

from django.apps import AppConfig
from django.db.models import Model
from django.test import override_settings
from django.test import TestCase

import csv_permissions.evaluators
import csv_permissions.permissions
from csv_permissions.test_utils import override_csv_permissions

from .models import TestModelA
from .test_utils import USER1_TYPE
from .test_utils import User1Factory
from .test_utils import USER2_TYPE
from .test_utils import User2Factory


def custom_resolve_perm_name(app_config: AppConfig, model: Type[Model], action: str, is_global: bool) -> str:
    app_label = app_config.label.upper()
    model_name = model._meta.object_name
    perm_name = f"{app_label}/{model_name}/{action}/{is_global}"
    return perm_name


@override_settings(
    CSV_PERMISSIONS_STRICT=True,
    CSV_PERMISSIONS_RESOLVE_EVALUATORS=[
        csv_permissions.evaluators.resolve_validation_evaluator,
        csv_permissions.evaluators.resolve_all_evaluator,
        csv_permissions.evaluators.resolve_yes_evaluator,
        csv_permissions.evaluators.resolve_empty_evaluator,
        csv_permissions.evaluators.resolve_fallback_not_implemented_evaluator
    ],
)
class CsvParsingTests(TestCase):
    def test_non_existent_permission_error(self):
        """
        Test what happens when permissions aren't present in the file
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         own,
        """.strip()

        with self.assertWarnsRegex(UserWarning, r"not implemented for test_csv_permissions.detail_testmodela"):
            user = User1Factory()
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
            user = User1Factory()

            with self.assertRaisesMessage(ValueError, "Empty permissions file"):
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
            user1 = User1Factory()
            user2 = User2Factory()

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
                user = User1Factory(email="user@localhost.test")

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
        user = User1Factory()

        with override_csv_permissions([csv_header_data + "\n" * 3 + "#" + csv_bad_line]):
            self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            with override_csv_permissions([csv_header_data + "\n" * 3 + csv_bad_line]):
                self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        with override_csv_permissions([csv_header_data + "\n" * 3 + "//" + csv_bad_line]):
            self.assertFalse(user.has_perm("test_csv_permissions.approve_testmodela", None))

        pass

    def test_misconfigured_object_permission_error(self):
        """
        Test that a permission which should be global level, raises an error if configured as a object permission.
        """
        csv_data = f"""
        Model,      App,                  Action, Is Global,    {USER1_TYPE},
        TestModelA, test_csv_permissions, list,   no,           yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            with self.assertRaisesMessage(RuntimeError, "object-level"):
                csv_permissions.permissions.CSVPermissionsBackend()

    @override_settings(CSV_PERMISSIONS_STRICT=False)
    def test_resolve_perm_name(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelE, test_csv_permissions, list,     yes,        yes,
        """.strip()

        user = User2Factory()

        with override_csv_permissions([csv_data]):
            # check default permission names
            self.assertTrue(user.has_perm("test_csv_permissions.list_testmodele"))
            self.assertFalse(user.has_perm("test_csv_permissions.list_testmodela"))

            with override_settings(
                CSV_PERMISSIONS_RESOLVE_PERM_NAME=("test_csv_permissions.test_parse.custom_resolve_perm_name")
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

        user1 = User1Factory()
        user2 = User2Factory()
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

        user1 = User1Factory()

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
        TestModelA, test_csv_permissions, foo,      yes,        ,
        """.strip()

        user1 = User1Factory()

        # consistent CSV files
        with override_csv_permissions([csv_data1, csv_data1]):
            self.assertTrue(user1.has_perm("test_csv_permissions.foo_testmodela"))

        # inconsistent CSV files
        with self.assertRaisesRegex(ValueError, 'inconsistent with a previous CSV file'):
            with override_csv_permissions([csv_data1, csv_data2]):
                csv_permissions.permissions.CSVPermissionsBackend()

    def test_empty_user_type(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  , {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,        ,  yes,
        """.strip()

        user1 = User1Factory()
        user_empty = User2Factory()
        user_empty.user_type = ""

        with override_csv_permissions([csv_data]):
            self.assertTrue(user1.has_perm("test_csv_permissions.foo_testmodela"))

            with override_settings(CSV_PERMISSIONS_STRICT=True):
                with self.assertRaises(LookupError):
                    user_empty.has_perm("test_csv_permissions.foo_testmodela")

            with override_settings(CSV_PERMISSIONS_STRICT=False):
                self.assertFalse(user_empty.has_perm("test_csv_permissions.foo_testmodela"))

    def test_empty_user_type_not_empty_column(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  ,     {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,        all,  yes,
        """.strip()

        with self.assertRaisesRegex(ValueError, 'empty user_type'):
            with override_csv_permissions([csv_data]):
                csv_permissions.permissions.CSVPermissionsBackend()

    def test_duplicate_header(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  , {USER1_TYPE}, {USER1_TYPE}, ,
        TestModelA, test_csv_permissions, foo,      yes,        , yes,          yes,          ,
        """.strip()

        with self.assertRaisesRegex(ValueError, f'Duplicate.*{USER1_TYPE}'):
            with override_csv_permissions([csv_data]):
                csv_permissions.permissions.CSVPermissionsBackend()

    def test_custom_get_user_type(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE}, {USER2_TYPE},
        TestModelA, test_csv_permissions, foo,      yes,        yes,          ,
        TestModelA, test_csv_permissions, bar,      yes,        ,             yes,
        """.strip()

        # we're going to use 'first_name' as the user_type
        # and that will make user1 & user2's permissions be swapped
        user1 = User1Factory(first_name=USER2_TYPE)

        with override_csv_permissions([csv_data]):
            self.assertTrue(user1.has_perm("test_csv_permissions.foo_testmodela"))
            self.assertFalse(user1.has_perm("test_csv_permissions.bar_testmodela"))

            def get_user_type(user):
                return user.first_name

            # and now use a different field to make user1 look like they're a USER2_TYPE
            with override_settings(CSV_PERMISSIONS_GET_USER_TYPE=get_user_type):
                self.assertFalse(user1.has_perm("test_csv_permissions.foo_testmodela"))
                self.assertTrue(user1.has_perm("test_csv_permissions.bar_testmodela"))