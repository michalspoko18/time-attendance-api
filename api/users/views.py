from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

REFRESH_COOKIE_NAME = 'refresh_token'


@api_view(['POST'])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response(
            {"detail": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = get_user_model().objects.filter(email=email).first()
    if user is None or not user.check_password(password) or not user.is_active:
        return Response(
            {"detail": "Invalid credentials."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    refresh = RefreshToken.for_user(user)
    response = Response(
        {"access": str(refresh.access_token)},
        status=status.HTTP_200_OK,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=str(refresh),
        max_age=int(jwt_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        path='/',
    )
    return response


@api_view(['POST'])
def logout():
    response = Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/')
    return response


@api_view(['POST'])
def refresh_token(request):
    refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        return Response(
            {"detail": "Refresh token not provided."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        refresh = RefreshToken(refresh_token)
        new_access_token = str(refresh.access_token)
        response = Response({"access": new_access_token}, status=status.HTTP_200_OK)
        return response
    except Exception:
        return Response(
            {"detail": "Invalid refresh token."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
