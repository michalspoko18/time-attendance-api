from django.db import models


class ConsumedQrToken(models.Model):
    nonce = models.CharField(max_length=255, unique=True)
    employee_id = models.CharField(max_length=50)
    event_type = models.CharField(max_length=10)
    consumed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.employee_id}:{self.event_type}:{self.nonce}'
