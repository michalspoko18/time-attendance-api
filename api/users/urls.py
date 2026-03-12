from django.urls import path
from .views import login, refresh_token, logout, me

urlpatterns = [
    path('login/', login, name='login'),
    path('logout/', logout, name='logout'),
    path('token/refresh/', refresh_token, name='refresh-token'),
    path('me/', me, name='me'),
]
