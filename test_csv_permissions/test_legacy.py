from unittest.mock import patch

from django.apps import apps
from django.test import override_settings
from django.test import TestCase

import csv_permissions
import csv_permissions.legacy
import csv_permissions.permissions
from csv_permissions.test_utils import override_csv_permissions
import test_csv_permissions.rules

from .models import TestModelA
from .models import TestModelE
from .test_utils import USER1_TYPE
from .test_utils import User1Factory
from .test_utils import USER2_TYPE
from .test_utils import User2Factory
from .test_utils import warning_filter


@warning_filter("ignore", category=DeprecationWarning)
@override_settings(
    CSV_PERMISSIONS_STRICT=True,
    CSV_PERMISSIONS_RESOLVE_EVALUATORS=csv_permissions.legacy.resolve_evaluators,
)
class LegacyEvaluatorsTest(TestCase):

    @override_settings(CSV_PERMISSIONS_RESOLVE_EVALUATOR='csv_permissions.legacy.resolve_evaluators')
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
            user1 = User1Factory()
            user2 = User2Factory()

            expected_results = (
                # (model, permission, pass_model, has_perm(USER1)?, has_perm(USER2)? )
                ("TestModelA", "test_csv_permissions.detail_testmodela", True, True, True),
                ("TestModelB", "test_csv_permissions.change_testmodelb", True, True, False),
                ("TestModelC", "test_csv_permissions.detail_testmodelc", True, True, True),
                ("TestModelD", "test_csv_permissions.list_testmodeld", False, False, True),
                ("TestModelE", "test_csv_permissions.change_testmodele", True, True, False),
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

    def test_global_permission_error(self):
        """
        Test that a permission which should be object level,
        raises an error if configured as a global permission.
        """
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, detail,   yes,        yes,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = User1Factory()

            with self.assertRaisesMessage(RuntimeError, "Invalid action / global setting"):
                csv_permissions.permissions.CSVPermissionsBackend()

    def test_own_global_permission_error(self):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER1_TYPE},
        TestModelA, test_csv_permissions, foo,   yes,        own,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = User1Factory()

            with self.assertRaises(RuntimeError):
                csv_permissions.permissions.CSVPermissionsBackend()

    @patch(
        "csv_permissions.legacy.evaluate_own",
        wraps=csv_permissions.legacy.evaluate_own,
    )
    def test_own_permission(self, evaluate_own_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelA, test_csv_permissions, detail,   no,         own: model_a,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = User2Factory()

            self.raises = self.assertRaisesRegex(ValueError, 'global permission')
            with self.raises:
                user.has_perm("test_csv_permissions.detail_testmodela")

            self.assertEqual(
                1,
                evaluate_own_mock.call_count,
                "Own function should have been called once",
            )

            test_obj = TestModelA.objects.create()
            self.assertTrue(
                user.has_perm("test_csv_permissions.detail_testmodela", test_obj),
                "User should have access to all objects",
            )

            self.assertEqual(
                2,
                evaluate_own_mock.call_count,
                "Own function should have been called twice",
            )

    @patch(
        "test_csv_permissions.rules.own_model_a_or_model_b",
        wraps=test_csv_permissions.rules.own_model_a_or_model_b,
    )
    def test_custom_permission(self, evaluate_custom_mock):
        csv_data = f"""
        Model,      App,                  Action,   Is Global,  {USER2_TYPE},
        TestModelE, test_csv_permissions, change,   no,         custom: own_model_a_or_model_b,
        """.strip()

        with override_csv_permissions([csv_data]):
            user = User2Factory()

            self.assertFalse(
                user.has_perm("test_csv_permissions.change_testmodele", None),
                "User should not have access with no object",
            )

            self.assertEqual(
                1,
                evaluate_custom_mock.call_count,
                "Custom function should have been called once",
            )

            test_obj = TestModelE.objects.create()
            self.assertFalse(
                user.has_perm("test_csv_permissions.change_testmodele", test_obj),
                "User should not have access to a specific object",
            )

            self.assertEqual(
                2,
                evaluate_custom_mock.call_count,
                "Custom function should have been called twice",
            )
