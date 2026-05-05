from django.urls import path

from .views import (
    generate_qrcode,
    manager_daily,
    manager_overview,
    manager_user_daily_breakdown,
    manager_user_detail,
    manager_user_sessions,
    manager_users_list,
    scan_status,
    stats_sessions,
    stats_summary,
    verify,
)

urlpatterns = [
    path('generate_qrcode/', generate_qrcode, name='attendance-generate-qrcode'),
    path('verify/', verify, name='attendance-verify'),
    path('scan-status/', scan_status, name='attendance-scan-status'),
    path('stats/summary/', stats_summary, name='attendance-stats-summary'),
    path('stats/sessions/', stats_sessions, name='attendance-stats-sessions'),
    # Manager endpoints
    path('manager/overview/', manager_overview, name='manager-overview'),
    path('manager/daily/', manager_daily, name='manager-daily'),
    path('manager/users/', manager_users_list, name='manager-users-list'),
    path('manager/users/<str:employee_id>/', manager_user_detail, name='manager-user-detail'),
    path('manager/users/<str:employee_id>/sessions/', manager_user_sessions, name='manager-user-sessions'),
    path('manager/users/<str:employee_id>/daily-breakdown/', manager_user_daily_breakdown, name='manager-user-daily-breakdown'),
]
