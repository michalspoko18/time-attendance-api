from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .tokens import issue_attendance_qr_token


class AttendanceQrFlowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='attendance-user',
            email='attendance@example.com',
            employee_id='EMP-2000',
            employment='FT',
            is_active=True,
            password='Str0ngP@ssword!',
        )
        self.generate_url = reverse('attendance-generate-qrcode')
        self.verify_url = reverse('attendance-verify')
        self.client.force_authenticate(user=self.user)

    def test_generate_qrcode_success(self):
        response = self.client.post(
            self.generate_url,
            {'event_type': 'entry'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('qr_token', response.data)
        self.assertEqual(set(response.data.keys()), {'qr_token'})

    def test_generate_qrcode_invalid_event_type_returns_400(self):
        response = self.client.post(
            self.generate_url,
            {'event_type': 'break'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_success_for_fresh_generated_token(self):
        generate_response = self.client.post(
            self.generate_url,
            {'event_type': 'exit'},
            format='json',
        )
        token = generate_response.data['qr_token']

        verify_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.data['valid'])
        self.assertEqual(verify_response.data['event_type'], 'exit')
        self.assertEqual(set(verify_response.data.keys()), {'valid', 'event_type'})

    def test_verify_tampered_token_returns_400(self):
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='entry',
        )

        response = self.client.post(
            self.verify_url,
            {'qr_token': f'{token}tampered'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_token_for_missing_employee_returns_404(self):
        token, _payload = issue_attendance_qr_token(
            employee_id='EMP-UNKNOWN',
            event_type='entry',
        )

        response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_generate_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.generate_url,
            {'event_type': 'entry'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verify_requires_authentication(self):
        self.client.force_authenticate(user=None)
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='entry',
        )

        response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
