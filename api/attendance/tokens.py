import secrets

from django.conf import settings
from django.core import signing

ATTENDANCE_QR_SIGNING_SALT = 'attendance.qr.token'
ALLOWED_EVENT_TYPES = {'entry', 'exit'}


def issue_attendance_qr_token(employee_id, event_type):
    payload = {
        'employee_id': employee_id,
        'event_type': event_type,
        'nonce': secrets.token_urlsafe(12),
    }
    token = signing.dumps(payload, salt=ATTENDANCE_QR_SIGNING_SALT)
    return token, payload


def verify_attendance_qr_token(token):
    max_age = settings.ATTENDANCE_QR_TOKEN_MAX_AGE_SECONDS
    payload = signing.loads(
        token,
        salt=ATTENDANCE_QR_SIGNING_SALT,
        max_age=max_age,
    )
    validate_attendance_payload(payload)
    return payload


def validate_attendance_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid QR token payload.')

    employee_id = payload.get('employee_id')
    event_type = payload.get('event_type')
    nonce = payload.get('nonce')

    if not employee_id or not isinstance(employee_id, str):
        raise ValueError('Token payload is missing employee_id.')
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError('Token payload contains unsupported event_type.')
    if not nonce or not isinstance(nonce, str):
        raise ValueError('Token payload is missing nonce.')
