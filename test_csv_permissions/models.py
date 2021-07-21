from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class User(AbstractBaseUser, PermissionsMixin):
    objects = BaseUserManager()

    USERNAME_FIELD = "email"

    email = models.EmailField(unique=True)

    USER_TYPE_CUSTOMER = "customer"
    USER_TYPE_STAFF = "staff"
    USER_TYPE_CHOICES = (
        (USER_TYPE_CUSTOMER, "Customer"),
        (USER_TYPE_STAFF, "Staff"),
    )

    user_type = models.CharField(max_length=255, choices=USER_TYPE_CHOICES)

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
