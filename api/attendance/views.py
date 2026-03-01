from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .tokens import ALLOWED_EVENT_TYPES, issue_attendance_qr_token, verify_attendance_qr_token


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
@permission_classes([IsAuthenticated])
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

    user_exists = get_user_model().objects.filter(
        employee_id=payload['employee_id'],
        is_active=True,
    ).exists()
    if not user_exists:
        return Response(
            {'detail': 'Token employee_id is not assigned to an active user.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            'valid': True,
            'employee_id': payload['employee_id'],
            'event_type': payload['event_type'],
            'nonce': payload['nonce'],
        },
        status=status.HTTP_200_OK,
    )
