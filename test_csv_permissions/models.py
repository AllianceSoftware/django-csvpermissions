from authtools.models import User
from django.db import models

class CustomerProfile(User):
    user_type='customer'
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    def get_profile(self):
        return self

class StaffProfile(User):
    user_type = 'staff'
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    def get_profile(self):
        return self

class TestModelA(models.Model):
    class Meta:
        default_permissions = ()


class TestModelB(models.Model):
    class Meta:
        default_permissions = ()


class TestModelC(models.Model):
    class Meta:
        default_permissions = ()


class TestModelD(models.Model):
    class Meta:
        default_permissions = ()


class TestModelE(models.Model):
    class Meta:
        default_permissions = ()
