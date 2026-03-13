# time-attendance-api

## Uruchomienie (Docker + PostgreSQL)

1. Skopiuj konfigurację środowiska:

```bash
cp .env.example .env
```

2. Zbuduj i uruchom kontenery:

```bash
docker compose up --build
```

3. Sprawdź endpoint API:

```bash
curl http://localhost:8000/api/health/
```

Powinieneś dostać:

```json
{"status":"ok"}
```

## Attendance QR API

`generate_qrcode` oraz `scan-status` wymagają uwierzytelnienia JWT (`Authorization: Bearer <access_token>`).
`verify` jest tymczasowo dostępne bez JWT.

Pobranie danych zalogowanego użytkownika:

```bash
curl http://localhost:8000/api/auth/me/ \
  -H "Authorization: Bearer <access_token>"
```

Generowanie tokenu QR:

```bash
curl -X POST http://localhost:8000/api/attendance/generate_qrcode/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"entry"}'
```

Weryfikacja tokenu QR:

```bash
curl -X POST http://localhost:8000/api/attendance/verify/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"<token-z-generate_qrcode>"}'
```

Sprawdzenie statusu skanu (polling):

```bash
curl -X GET "http://localhost:8000/api/attendance/scan-status/?qr_token=<token-z-generate_qrcode>" \
  -H "Authorization: Bearer <access_token>"
```

Przykładowe odpowiedzi:

```json
{"status":"pending","scanned":false,"event_type":"entry","scanned_at":null}
```

```json
{"status":"ok","scanned":true,"event_type":"entry","scanned_at":"2026-03-13T18:00:00Z"}
```

## Attendance Stats API

Podsumowanie czasu pracy zalogowanego użytkownika:

```bash
curl -X GET "http://localhost:8000/api/attendance/stats/summary/?date_from=2026-03-01&date_to=2026-03-31" \
  -H "Authorization: Bearer <access_token>"
```

Lista sesji pracy z filtrami i paginacją:

```bash
curl -X GET "http://localhost:8000/api/attendance/stats/sessions/?status=closed&page=1&page_size=20" \
  -H "Authorization: Bearer <access_token>"
```

## Przydatne komendy

Domyślne konto admina (ładowane automatycznie z fixture przy starcie):

- login: `admin`
- hasło: `admin123`

Ręczne tworzenie dodatkowego superusera:

```bash
docker compose exec app python api/manage.py createsuperuser
```

Zatrzymanie i usunięcie kontenerów + wolumenów:

```bash
docker compose down -v
```
