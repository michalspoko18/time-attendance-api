from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=50, unique=True)

    class employment_type(models.TextChoices):
        FULL_TIME = 'FT', 'Full Time'
        PART_TIME = 'PT', 'Part Time'

    employment = models.CharField(
        max_length=2,
        choices=employment_type.choices
    )
    is_manager = models.BooleanField(default=False)
