from django.contrib.auth import get_user_model


def authenticate_user_by_email(email, password):
    if not email or not password:
        return None

    user = get_user_model().objects.filter(email=email).first()
    if user is None or not user.check_password(password) or not user.is_active:
        return None

    return user
