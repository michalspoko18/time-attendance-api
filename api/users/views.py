from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .utils import authenticate_user_by_email

from .tokens import (
    clear_refresh_cookie,
    get_refresh_token_from_request,
    issue_tokens_for_user,
    set_refresh_cookie,
)


@api_view(['POST'])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response(
            {"detail": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate_user_by_email(email=email, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid credentials."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    tokens = issue_tokens_for_user(user)
    response = Response(
        {"access": tokens['access']},
        status=status.HTTP_200_OK,
    )
    set_refresh_cookie(response, tokens['refresh'])
    return response


@api_view(['POST'])
def logout(_request):
    response = Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)
    clear_refresh_cookie(response)
    return response


@api_view(['POST'])
def refresh_token(request):
    refresh_token = get_refresh_token_from_request(request)
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
