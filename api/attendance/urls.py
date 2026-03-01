from django.urls import path

from .views import generate_qrcode, verify

urlpatterns = [
    path('generate_qrcode/', generate_qrcode, name='attendance-generate-qrcode'),
    path('verify/', verify, name='attendance-verify'),
]
