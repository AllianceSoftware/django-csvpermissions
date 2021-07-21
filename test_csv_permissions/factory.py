import factory

from test_csv_permissions.models import User


class UserFactory(factory.django.DjangoModelFactory):
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    @factory.post_generation
    def password(record: User, create: bool, extracted, **kwargs):
        if extracted is not None:
            password = extracted
        else:
            password = User.objects.make_random_password()
        record.set_password(password)
        record._unencrypted_password = password

    @factory.sequence
    def email(n):
        return f"email-{n}@example.com"

    @classmethod
    def _after_postgeneration(cls, instance: User, create: bool, results=None):
        super()._after_postgeneration(instance, create, results)
        if create:
            # restore _password after save() wipes it
            instance._password = instance._unencrypted_password
            delattr(instance, "_unencrypted_password")

    class Meta:
        model = User
