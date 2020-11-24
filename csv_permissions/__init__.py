import unittest

default_app_config = 'csv_permissions.apps.CsvPermissionAppConfig'

def load_tests(*args, **kwargs):
  empty_suite = unittest.TestSuite()
  return empty_suite
