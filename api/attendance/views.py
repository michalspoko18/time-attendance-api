from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Sum
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ConsumedQrToken, WorkSession
from .tokens import ALLOWED_EVENT_TYPES, issue_attendance_qr_token, verify_attendance_qr_token


def _parse_stats_filters(request):
    date_from_raw = request.query_params.get('date_from')
    date_to_raw = request.query_params.get('date_to')
    status_filter = request.query_params.get('status')

    date_from = None
    if date_from_raw:
        date_from = parse_date(date_from_raw)
        if date_from is None:
            return None, Response(
                {'detail': 'Invalid date_from. Expected YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    date_to = None
    if date_to_raw:
        date_to = parse_date(date_to_raw)
        if date_to is None:
            return None, Response(
                {'detail': 'Invalid date_to. Expected YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if date_from and date_to and date_from > date_to:
        return None, Response(
            {'detail': 'date_from cannot be greater than date_to.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if status_filter and status_filter not in {'open', 'closed'}:
        return None, Response(
            {'detail': "Invalid status. Allowed values: 'open', 'closed'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return {
        'date_from': date_from,
        'date_to': date_to,
        'status': status_filter,
    }, None


def _get_filtered_sessions(user, filters):
    sessions = WorkSession.objects.filter(user=user)

    if filters['date_from']:
        sessions = sessions.filter(started_at__date__gte=filters['date_from'])
    if filters['date_to']:
        sessions = sessions.filter(started_at__date__lte=filters['date_to'])
    if filters['status'] == 'open':
        sessions = sessions.filter(ended_at__isnull=True)
    if filters['status'] == 'closed':
        sessions = sessions.filter(ended_at__isnull=False)

    return sessions


def _serialize_session(session):
    return {
        'id': session.id,
        'started_at': session.started_at,
        'ended_at': session.ended_at,
        'duration_seconds': session.duration_seconds,
        'status': 'open' if session.ended_at is None else 'closed',
    }


class WorkSessionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_qrcode(request):
    event_type = request.data.get('event_type')

    if not event_type:
        return Response(
            {'detail': 'event_type is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if event_type not in ALLOWED_EVENT_TYPES:
        return Response(
            {
                'detail': 'Unsupported event_type.',
                'allowed_event_types': sorted(ALLOWED_EVENT_TYPES),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    employee_id = request.user.employee_id
    if request.auth is not None:
        employee_id = request.auth.get('employee_id', employee_id)

    user = get_user_model().objects.filter(employee_id=employee_id, is_active=True).first()
    if user is None:
        return Response(
            {'detail': 'Active user with given employee_id was not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    qr_token, _payload = issue_attendance_qr_token(employee_id=user.employee_id, event_type=event_type)
    return Response(
        {'qr_token': qr_token},
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
def verify(request):
    qr_token = request.data.get('qr_token')
    if not qr_token:
        return Response(
            {'detail': 'qr_token is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payload = verify_attendance_qr_token(qr_token)
    except SignatureExpired:
        return Response({'detail': 'QR token expired.'}, status=status.HTTP_400_BAD_REQUEST)
    except BadSignature:
        return Response({'detail': 'Invalid QR token signature.'}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user = get_user_model().objects.filter(
        employee_id=payload['employee_id'],
        is_active=True,
    ).first()
    if user is None:
        return Response(
            {'detail': 'Token employee_id is not assigned to an active user.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    session_to_close = None
    if payload['event_type'] == 'entry':
        open_session_exists = WorkSession.objects.filter(user=user, ended_at__isnull=True).exists()
        if open_session_exists:
            return Response(
                {'detail': 'Cannot start work: open session already exists.'},
                status=status.HTTP_409_CONFLICT,
            )

    if payload['event_type'] == 'exit':
        session_to_close = WorkSession.objects.filter(user=user, ended_at__isnull=True).order_by('started_at').first()
        if session_to_close is None:
            return Response(
                {'detail': 'Cannot end work: no open session found.'},
                status=status.HTTP_409_CONFLICT,
            )

    try:
        with transaction.atomic():
            ConsumedQrToken.objects.create(
                nonce=payload['nonce'],
                employee_id=payload['employee_id'],
                event_type=payload['event_type'],
            )
            if payload['event_type'] == 'entry':
                WorkSession.objects.create(user=user)
            if payload['event_type'] == 'exit':
                session_to_close.ended_at = timezone.now()
                duration_seconds = int(
                    (session_to_close.ended_at - session_to_close.started_at).total_seconds()
                )
                session_to_close.duration_seconds = max(duration_seconds, 0)
                session_to_close.save(update_fields=['ended_at', 'duration_seconds'])
    except IntegrityError:
        return Response(
            {'detail': 'QR token already used.'},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            'valid': True,
            'event_type': payload['event_type'],
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def scan_status(request):
    qr_token = request.query_params.get('qr_token')
    if not qr_token:
        return Response(
            {'detail': 'qr_token is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payload = verify_attendance_qr_token(qr_token)
    except SignatureExpired:
        return Response({'detail': 'QR token expired.'}, status=status.HTTP_400_BAD_REQUEST)
    except BadSignature:
        return Response({'detail': 'Invalid QR token signature.'}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    request_employee_id = request.user.employee_id
    if request.auth is not None:
        request_employee_id = request.auth.get('employee_id', request_employee_id)

    if payload['employee_id'] != request_employee_id:
        return Response(
            {'detail': 'You do not have access to this QR token.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    consumed_token = ConsumedQrToken.objects.filter(nonce=payload['nonce']).first()
    is_scanned = consumed_token is not None
    return Response(
        {
            'status': 'ok' if is_scanned else 'pending',
            'scanned': is_scanned,
            'event_type': payload['event_type'],
            'scanned_at': consumed_token.consumed_at if consumed_token else None,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_summary(request):
    filters, error_response = _parse_stats_filters(request)
    if error_response:
        return error_response

    sessions = _get_filtered_sessions(request.user, filters)
    aggregate = sessions.aggregate(total_duration_seconds=Sum('duration_seconds'))

    return Response(
        {
            'total_duration_seconds': aggregate['total_duration_seconds'] or 0,
            'worked_sessions_count': sessions.filter(ended_at__isnull=False).count(),
            'open_sessions_count': sessions.filter(ended_at__isnull=True).count(),
            'total_sessions_count': sessions.count(),
            'filters': {
                'date_from': filters['date_from'].isoformat() if filters['date_from'] else None,
                'date_to': filters['date_to'].isoformat() if filters['date_to'] else None,
                'status': filters['status'],
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_sessions(request):
    filters, error_response = _parse_stats_filters(request)
    if error_response:
        return error_response

    sessions = _get_filtered_sessions(request.user, filters).order_by('-started_at', '-id')
    paginator = WorkSessionPagination()
    page = paginator.paginate_queryset(sessions, request)
    serialized_sessions = [_serialize_session(session) for session in page]
    return paginator.get_paginated_response(serialized_sessions)
