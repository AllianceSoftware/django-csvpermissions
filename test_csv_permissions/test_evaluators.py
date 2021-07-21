from unittest.mock import patch

from django.apps import apps
from django.test import override_settings
from django.test import TestCase

import csv_permissions.evaluators
import csv_permissions.legacy
import csv_permissions.permissions

from .models import TestModelA
from .models import TestModelD
from .test_utils import override_csv_permissions
from .test_utils import USER1_TYPE
from .test_utils import User1Factory
from .test_utils import USER2_TYPE
from .test_utils import User2Factory


@override_settings(
    CSV_PERMISSIONS_STRICT=True,
    CSV_PERMISSIONS_RESOLVE_EVALUATORS=csv_permissions.evaluators.default_resolve_evaluators,
)
class EvaluatorsTest(TestCase):

    @override_settings(CSV_PERMISSIONS_RESOLVE_EVALUATOR='csv_permissions.legacy.resolve_evaluators')
    def test_permissions_parse(self):
        """
        Does not test implementations of individual permissions functions, only that they have been loaded correctly
        from the CSV. yes/no/all have fixed return values, whereas own/custom functions are defined in rules.py.
        """

        csv_data = f"""
        Model,      App,                  Action, Is Global, {USER1_TYPE},  {USER2_TYPE},
        TestModelA, test_csv_permissions, detail, no,        all,           ,
        TestModelB, test_csv_permissions, change, no,        ,              ,
        TestModelC, test_csv_permissions, detail, no,        all,           all,
        TestModelD, test_csv_permissions, list,   yes,       ,              yes,
        TestModelE, test_csv_permissions, change, no,        ,              ,
        """.strip()

        with override_csv_permissions([csv_data]):
            user1 = User1Factory()
            user2 = User2Factory()

            expected_results = (
                # (model, permission, pass_model, has_perm(USER1)?, has_perm(USER2)? )
                ("TestModelA", "test_csv_permissions.detail_testmodela", True, True, False),
                ("TestModelB", "test_csv_permissions.change_testmodelb", True, False, False),
                ("TestModelC", "test_csv_permissions.detail_testmodelc", True, True, True),
                ("TestModelD", "test_csv_permissions.list_testmodeld", False, False, True),
                ("TestModelE", "test_csv_permissions.change_testmodele", True, False, False),
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
            user = User1Factory()

            with self.assertRaisesRegex(RuntimeError, 'global'):
                csv_permissions.permissions.CSVPermissionsBackend()

    def test_yes_object_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = User1Factory()

            with self.assertRaises(RuntimeError):
                csv_permissions.permissions.CSVPermissionsBackend()

    @patch(
        "csv_permissions.evaluators.evaluate_all",
        wraps=csv_permissions.evaluators.evaluate_all,
    )
    def test_all_permission(self, evaluate_all_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         all,
        """.strip()

        user = User1Factory()

        with override_csv_permissions([csv_data]):
            csv_permissions.permissions.CSVPermissionsBackend()

            with self.assertRaises(ValueError):
                user.has_perm("test_csv_permissions.detail_testmodela", None)

            self.assertEqual(
                1,
                evaluate_all_mock.call_count,
                "All function should have been called once",
            )

            test_obj = TestModelA.objects.create()
            self.assertTrue(
                user.has_perm("test_csv_permissions.detail_testmodela", test_obj),
                "User should have access to all objects",
            )

            self.assertEqual(
                2,
                evaluate_all_mock.call_count,
                "All function should have been called twice",
            )

    @patch(
        "csv_permissions.evaluators.evaluate_yes",
        wraps=csv_permissions.evaluators.evaluate_yes,
    )
    def test_yes_permission(self, evaluate_yes_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelD, test_csv_permissions, list,     yes,        yes,
        """.strip()

        user = User2Factory()

        with override_csv_permissions([csv_data]):
            csv_permissions.permissions.CSVPermissionsBackend()

            self.assertTrue(
                user.has_perm("test_csv_permissions.list_testmodeld", None),
                "User should have access with no object",
            )

            self.assertEqual(
                1,
                evaluate_yes_mock.call_count,
                "Yes function should have been called once",
            )

            test_obj = TestModelD.objects.create()
            with self.assertRaises(ValueError):
                user.has_perm("test_csv_permissions.list_testmodeld", test_obj)

            self.assertEqual(
                2,
                evaluate_yes_mock.call_count,
                "Yes function should have been called twice",
            )

    @patch(
        "csv_permissions.evaluators.evaluate_no",
        wraps=csv_permissions.evaluators.evaluate_no,
    )
    def test_no_permission(self, evaluate_no_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelD, test_csv_permissions, list,     yes,        ,
        """.strip()

        user = User1Factory()

        with override_csv_permissions([csv_data]):

            self.assertFalse(
                user.has_perm("test_csv_permissions.list_testmodeld", None),
                "User should not have access with no object",
            )

            self.assertEqual(
                1,
                evaluate_no_mock.call_count,
                "No function should have been called once",
            )

            test_obj = TestModelD.objects.create()
            self.assertFalse(
                user.has_perm("test_csv_permissions.list_testmodeld", test_obj),
                "User should not have access with no object",
            )

            self.assertEqual(
                2,
                evaluate_no_mock.call_count,
                "No function should have been called twice",
            )
