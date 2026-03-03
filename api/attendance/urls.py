from django.urls import path

from .views import generate_qrcode, stats_sessions, stats_summary, verify

urlpatterns = [
    path('generate_qrcode/', generate_qrcode, name='attendance-generate-qrcode'),
    path('verify/', verify, name='attendance-verify'),
    path('stats/summary/', stats_summary, name='attendance-stats-summary'),
    path('stats/sessions/', stats_sessions, name='attendance-stats-sessions'),
]
