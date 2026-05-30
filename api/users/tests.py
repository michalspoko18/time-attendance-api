from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .tokens import REFRESH_COOKIE_NAME
from .utils import authenticate_user_by_email


class LoginViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('login')
        self.password = 'Str0ngP@ssword!'
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            employee_id='EMP-1000',
            employment='FT',
            is_active=True,
        )
        self.user.set_password(self.password)
        self.user.save()

    def test_login_success_returns_access_and_sets_refresh_cookie(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[REFRESH_COOKIE_NAME]['httponly'])

    def test_login_with_invalid_password_returns_401(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': 'wrong-password'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_missing_fields_returns_400(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_inactive_user_returns_401(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_access_token_is_decodable(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_token = response.data['access']
        token = AccessToken(access_token)

        self.assertEqual(int(token['user_id']), self.user.id)
        self.assertEqual(token['employee_id'], self.user.employee_id)


class MeViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('me')
        self.user = get_user_model().objects.create_user(
            username='me-user',
            first_name='Jan',
            last_name='Kowalski',
            email='me@example.com',
            employee_id='EMP-3000',
            employment='PT',
            is_active=True,
            password='Str0ngP@ssword!',
        )

    def test_me_returns_authenticated_user_data(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                'id': self.user.id,
                'username': self.user.username,
                'first_name': self.user.first_name,
                'last_name': self.user.last_name,
                'email': self.user.email,
                'employee_id': self.user.employee_id,
                'employment': self.user.employment,
                'is_active': self.user.is_active,
                'is_manager': self.user.is_manager,
            },
        )

    def test_me_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('logout')

    def test_logout_returns_200_and_clears_cookie(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(REFRESH_COOKIE_NAME, response.cookies)


class RefreshTokenViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('refresh-token')
        self.password = 'Str0ngP@ssword!'
        self.user = get_user_model().objects.create_user(
            username='refresh-user',
            email='refresh@example.com',
            employee_id='EMP-5000',
            employment='FT',
            is_active=True,
        )
        self.user.set_password(self.password)
        self.user.save()

    def _get_refresh_token(self):
        response = self.client.post(
            reverse('login'),
            {'email': self.user.email, 'password': self.password},
            format='json',
        )
        return response.cookies[REFRESH_COOKIE_NAME].value

    def test_refresh_with_valid_cookie_returns_new_access_token(self):
        self.client.cookies[REFRESH_COOKIE_NAME] = self._get_refresh_token()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_refresh_without_cookie_returns_401(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_invalid_token_returns_401(self):
        self.client.cookies[REFRESH_COOKIE_NAME] = 'bad-token-value'
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticateUserByEmailTests(TestCase):
    """Direct unit tests for authenticate_user_by_email (users/utils.py)."""

    def test_returns_none_for_empty_email(self):
        result = authenticate_user_by_email(email='', password='somepassword')
        self.assertIsNone(result)

    def test_returns_none_for_empty_password(self):
        result = authenticate_user_by_email(email='someone@example.com', password='')
        self.assertIsNone(result)
