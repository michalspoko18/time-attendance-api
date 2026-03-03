from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import WorkSession
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

    def test_verify_success_for_entry_starts_work_session(self):
        generate_response = self.client.post(
            self.generate_url,
            {'event_type': 'entry'},
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
        self.assertEqual(verify_response.data['event_type'], 'entry')
        self.assertEqual(set(verify_response.data.keys()), {'valid', 'event_type'})
        open_session = WorkSession.objects.filter(user=self.user, ended_at__isnull=True).first()
        self.assertIsNotNone(open_session)

    def test_verify_success_for_exit_ends_open_work_session(self):
        session = WorkSession.objects.create(user=self.user)
        session.started_at = timezone.now() - timedelta(hours=2)
        session.save(update_fields=['started_at'])

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
        open_session_exists = WorkSession.objects.filter(user=self.user, ended_at__isnull=True).exists()
        self.assertFalse(open_session_exists)
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertIsNotNone(session.duration_seconds)
        self.assertGreaterEqual(session.duration_seconds, 1)

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

    def test_verify_same_token_twice_returns_409_on_second_use(self):
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='entry',
        )

        first_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )
        second_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_409_CONFLICT)

    def test_verify_entry_when_open_session_exists_returns_409(self):
        WorkSession.objects.create(user=self.user)
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='entry',
        )

        response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_verify_entry_conflict_does_not_consume_token(self):
        open_session = WorkSession.objects.create(user=self.user)
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='entry',
        )

        first_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )
        open_session.ended_at = open_session.started_at
        open_session.save(update_fields=['ended_at'])
        second_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)


class AttendanceStatsTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='stats-user',
            email='stats@example.com',
            employee_id='EMP-3000',
            employment='FT',
            is_active=True,
            password='Str0ngP@ssword!',
        )
        self.other_user = user_model.objects.create_user(
            username='other-user',
            email='other@example.com',
            employee_id='EMP-4000',
            employment='FT',
            is_active=True,
            password='Str0ngP@ssword!',
        )
        self.summary_url = reverse('attendance-stats-summary')
        self.sessions_url = reverse('attendance-stats-sessions')
        self.client.force_authenticate(user=self.user)

    def _create_session(self, user, started_at, ended_at=None, duration_seconds=None):
        session = WorkSession.objects.create(
            user=user,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
        )
        session.started_at = started_at
        session.save(update_fields=['started_at'])
        return session

    def test_stats_summary_returns_only_authenticated_user_data(self):
        now = timezone.now()
        self._create_session(
            user=self.user,
            started_at=now - timedelta(hours=5),
            ended_at=now - timedelta(hours=3),
            duration_seconds=7200,
        )
        self._create_session(
            user=self.user,
            started_at=now - timedelta(hours=2),
            ended_at=now - timedelta(hours=1),
            duration_seconds=3600,
        )
        self._create_session(
            user=self.user,
            started_at=now - timedelta(minutes=30),
            ended_at=None,
            duration_seconds=None,
        )
        self._create_session(
            user=self.other_user,
            started_at=now - timedelta(hours=4),
            ended_at=now - timedelta(hours=2),
            duration_seconds=7200,
        )

        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_duration_seconds'], 10800)
        self.assertEqual(response.data['worked_sessions_count'], 2)
        self.assertEqual(response.data['open_sessions_count'], 1)
        self.assertEqual(response.data['total_sessions_count'], 3)

    def test_stats_summary_supports_date_filter(self):
        now = timezone.now()
        self._create_session(
            user=self.user,
            started_at=now - timedelta(days=2),
            ended_at=now - timedelta(days=2, hours=-1),
            duration_seconds=3600,
        )
        self._create_session(
            user=self.user,
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=1),
            duration_seconds=7200,
        )

        date_from = (now - timedelta(days=1)).date().isoformat()
        response = self.client.get(f'{self.summary_url}?date_from={date_from}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_duration_seconds'], 7200)
        self.assertEqual(response.data['total_sessions_count'], 1)

    def test_stats_summary_invalid_date_returns_400(self):
        response = self.client.get(f'{self.summary_url}?date_from=2026-13-99')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stats_sessions_is_paginated(self):
        base_time = timezone.now()
        for index in range(3):
            self._create_session(
                user=self.user,
                started_at=base_time - timedelta(hours=index + 1),
                ended_at=base_time - timedelta(hours=index),
                duration_seconds=3600,
            )

        response = self.client.get(f'{self.sessions_url}?page=1&page_size=2')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])
        self.assertIn('status', response.data['results'][0])

    def test_stats_sessions_supports_status_filter(self):
        now = timezone.now()
        self._create_session(
            user=self.user,
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=2),
            duration_seconds=3600,
        )
        self._create_session(
            user=self.user,
            started_at=now - timedelta(hours=1),
            ended_at=None,
            duration_seconds=None,
        )

        response = self.client.get(f'{self.sessions_url}?status=open')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'open')

    def test_stats_sessions_invalid_status_returns_400(self):
        response = self.client.get(f'{self.sessions_url}?status=invalid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_exit_without_open_session_returns_409(self):
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='exit',
        )

        response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_verify_exit_conflict_does_not_consume_token(self):
        token, _payload = issue_attendance_qr_token(
            employee_id=self.user.employee_id,
            event_type='exit',
        )

        first_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )
        WorkSession.objects.create(user=self.user)
        second_response = self.client.post(
            self.verify_url,
            {'qr_token': token},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
