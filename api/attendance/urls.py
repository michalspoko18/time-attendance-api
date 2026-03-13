from django.urls import path

from .views import generate_qrcode, scan_status, stats_sessions, stats_summary, verify

urlpatterns = [
    path('generate_qrcode/', generate_qrcode, name='attendance-generate-qrcode'),
    path('verify/', verify, name='attendance-verify'),
    path('scan-status/', scan_status, name='attendance-scan-status'),
    path('stats/summary/', stats_summary, name='attendance-stats-summary'),
    path('stats/sessions/', stats_sessions, name='attendance-stats-sessions'),
]
