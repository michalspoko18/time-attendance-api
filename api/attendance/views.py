from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Sum, Q
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
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


# ---------------------------------------------------------------------------
# Manager permission
# ---------------------------------------------------------------------------

class IsManager(BasePermission):
    """Allows access only to users with is_manager=True or is_staff=True."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (getattr(request.user, 'is_manager', False) or request.user.is_staff)
        )


# ---------------------------------------------------------------------------
# Manager helpers
# ---------------------------------------------------------------------------

def _today_session_data(user):
    """Return today's work data for a single user."""
    today = timezone.localdate()
    today_sessions = WorkSession.objects.filter(user=user, started_at__date=today)
    open_session = today_sessions.filter(ended_at__isnull=True).order_by('started_at').first()
    closed_aggregate = today_sessions.filter(ended_at__isnull=False).aggregate(
        total=Sum('duration_seconds')
    )
    closed_seconds = closed_aggregate['total'] or 0

    if open_session:
        running_seconds = int((timezone.now() - open_session.started_at).total_seconds())
        total_today_seconds = closed_seconds + max(running_seconds, 0)
        current_status = 'in'
        started_at = open_session.started_at
    else:
        total_today_seconds = closed_seconds
        current_status = 'out' if closed_seconds > 0 else 'absent'
        first_session = today_sessions.order_by('started_at').first()
        started_at = first_session.started_at if first_session else None

    return {
        'status': current_status,
        'started_at': started_at,
        'today_seconds': total_today_seconds,
    }


def _serialize_user_base(user):
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'employee_id': user.employee_id,
        'employment': user.employment,
        'is_active': user.is_active,
        'is_manager': user.is_manager,
    }


# ---------------------------------------------------------------------------
# Manager views
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_overview(request):
    """Global stats: user counts, today's attendance counts."""
    User = get_user_model()
    today = timezone.localdate()

    total_users = User.objects.filter(is_active=True).count()
    users_in = (
        WorkSession.objects.filter(started_at__date=today, ended_at__isnull=True)
        .values('user')
        .distinct()
        .count()
    )
    users_worked_today = (
        WorkSession.objects.filter(started_at__date=today)
        .values('user')
        .distinct()
        .count()
    )
    users_absent = total_users - users_worked_today

    return Response(
        {
            'total_users': total_users,
            'users_in': users_in,
            'users_worked_today': users_worked_today,
            'users_absent': users_absent,
            'date': today.isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_daily(request):
    """Today's attendance snapshot for every active employee."""
    User = get_user_model()
    users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    result = []
    for user in users:
        row = _serialize_user_base(user)
        row.update(_today_session_data(user))
        result.append(row)
    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_users_list(request):
    """List all users (active + inactive)."""
    User = get_user_model()
    is_active_param = request.query_params.get('is_active')
    qs = User.objects.all().order_by('last_name', 'first_name')
    if is_active_param is not None:
        qs = qs.filter(is_active=is_active_param.lower() in {'1', 'true', 'yes'})

    paginator = WorkSessionPagination()
    page = paginator.paginate_queryset(qs, request)
    data = [_serialize_user_base(u) for u in page]
    return paginator.get_paginated_response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_user_detail(request, employee_id):
    """User info + summary stats + today's status."""
    User = get_user_model()
    user = User.objects.filter(employee_id=employee_id).first()
    if user is None:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    today = timezone.localdate()
    week_start = today - timezone.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def _total_seconds(qs):
        return qs.filter(ended_at__isnull=False).aggregate(t=Sum('duration_seconds'))['t'] or 0

    all_sessions = WorkSession.objects.filter(user=user)
    today_data = _today_session_data(user)

    data = _serialize_user_base(user)
    data['stats'] = {
        'today_seconds': today_data['today_seconds'],
        'week_seconds': _total_seconds(all_sessions.filter(started_at__date__gte=week_start)),
        'month_seconds': _total_seconds(all_sessions.filter(started_at__date__gte=month_start)),
        'total_seconds': _total_seconds(all_sessions),
        'total_sessions': all_sessions.count(),
    }
    data['today'] = today_data
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_user_sessions(request, employee_id):
    """Paginated work sessions for a specific user, with optional date/status filters."""
    User = get_user_model()
    user = User.objects.filter(employee_id=employee_id).first()
    if user is None:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    filters, error_response = _parse_stats_filters(request)
    if error_response:
        return error_response

    sessions = _get_filtered_sessions(user, filters).order_by('-started_at', '-id')
    paginator = WorkSessionPagination()
    page = paginator.paginate_queryset(sessions, request)
    serialized = [_serialize_session(s) for s in page]
    return paginator.get_paginated_response(serialized)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def manager_user_daily_breakdown(request, employee_id):
    """Per-day hours worked for a user (last 30 days by default)."""
    User = get_user_model()
    user = User.objects.filter(employee_id=employee_id).first()
    if user is None:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    date_from_raw = request.query_params.get('date_from')
    date_to_raw = request.query_params.get('date_to')

    today = timezone.localdate()
    date_to = parse_date(date_to_raw) if date_to_raw else today
    date_from = parse_date(date_from_raw) if date_from_raw else (today - timezone.timedelta(days=29))

    if date_from is None or date_to is None:
        return Response({'detail': 'Invalid date format. Expected YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    from django.db.models.functions import TruncDate

    rows = (
        WorkSession.objects.filter(
            user=user,
            started_at__date__gte=date_from,
            started_at__date__lte=date_to,
            ended_at__isnull=False,
        )
        .annotate(day=TruncDate('started_at'))
        .values('day')
        .annotate(total_seconds=Sum('duration_seconds'))
        .order_by('day')
    )

    breakdown = [
        {'date': row['day'].isoformat(), 'total_seconds': row['total_seconds'] or 0}
        for row in rows
    ]
    return Response(breakdown, status=status.HTTP_200_OK)

