# time-attendance-api

Backend systemu rejestracji czasu pracy. REST API zbudowane w Django REST Framework z uwierzytelnianiem JWT i bazą danych PostgreSQL.

## Stos technologiczny

- **Django 6** + **Django REST Framework 3**
- **SimpleJWT** — uwierzytelnianie JWT
- **PostgreSQL** — baza danych
- **Docker** + **Docker Compose** — środowisko uruchomieniowe

## Uruchomienie

1. Skopiuj konfigurację środowiska:

```bash
cp .env.example .env
```

2. Zbuduj i uruchom kontenery:

```bash
docker compose up --build
```

3. Sprawdź działanie API:

```bash
curl http://localhost:8000/api/health/
# {"status":"ok"}
```

Panel administracyjny Django dostępny pod: `http://localhost:8000/admin/`

## Zmienne środowiskowe

| Zmienna                               | Opis                        | Domyślna wartość      |
| ------------------------------------- | --------------------------- | --------------------- |
| `DJANGO_SECRET_KEY`                   | Klucz sekretny Django       | —                     |
| `DJANGO_DEBUG`                        | Tryb debugowania            | `True`                |
| `DJANGO_ALLOWED_HOSTS`                | Dozwolone hosty (przecinek) | `localhost,127.0.0.1` |
| `POSTGRES_DB`                         | Nazwa bazy danych           | `time_attendance`     |
| `POSTGRES_USER`                       | Użytkownik bazy danych      | `time_attendance`     |
| `POSTGRES_PASSWORD`                   | Hasło bazy danych           | —                     |
| `POSTGRES_HOST`                       | Host bazy danych            | `db`                  |
| `POSTGRES_PORT`                       | Port bazy danych            | `5432`                |
| `ATTENDANCE_QR_TOKEN_MAX_AGE_SECONDS` | Czas życia tokenu QR (s)    | `300`                 |

## Testowanie — Postman

Kolekcja Postman dostępna w `postman/time-attendance-api.postman_collection.json`.

Aby zaimportować: **Postman → Import → wybierz plik**.

Kolekcja zawiera predefiniowane zmienne (`baseUrl`, `accessToken`, `refreshToken`, `qrToken`, `employeeId` i inne) oraz skrypty testowe, które automatycznie zapisują tokeny JWT po zalogowaniu i token QR po jego wygenerowaniu.

## Endpointy API

### Autentykacja — `/api/auth/`

| Metoda | URL                        | Opis                                       | Auth |
| ------ | -------------------------- | ------------------------------------------ | ---- |
| `POST` | `/api/auth/login/`         | Logowanie, zwraca JWT                      | Nie  |
| `POST` | `/api/auth/logout/`        | Wylogowanie (unieważnienie refresh tokenu) | Tak  |
| `POST` | `/api/auth/token/refresh/` | Odświeżenie access tokenu                  | Nie  |
| `GET`  | `/api/auth/me/`            | Dane zalogowanego użytkownika              | Tak  |

### Rejestracja obecności — `/api/attendance/`

| Metoda | URL                                | Opis                                    | Auth |
| ------ | ---------------------------------- | --------------------------------------- | ---- |
| `POST` | `/api/attendance/generate_qrcode/` | Generuje jednorazowy token QR           | Tak  |
| `POST` | `/api/attendance/verify/`          | Weryfikuje token QR (używane przez IoT) | Tak  |
| `GET`  | `/api/attendance/scan-status/`     | Sprawdzenie statusu skanu (polling)     | Tak  |

### Statystyki pracownika — `/api/attendance/stats/`

| Metoda | URL                               | Opis                                                             | Auth |
| ------ | --------------------------------- | ---------------------------------------------------------------- | ---- |
| `GET`  | `/api/attendance/stats/summary/`  | Podsumowanie czasu pracy (`?date_from=&date_to=`)                | Tak  |
| `GET`  | `/api/attendance/stats/sessions/` | Lista sesji z filtrami i paginacją (`?status=&page=&page_size=`) | Tak  |

### Panel managera — `/api/attendance/manager/`

| Metoda | URL                                                   | Opis                        | Auth          |
| ------ | ----------------------------------------------------- | --------------------------- | ------------- |
| `GET`  | `/api/attendance/manager/overview/`                   | Ogólny przegląd zespołu     | Tak (manager) |
| `GET`  | `/api/attendance/manager/daily/`                      | Dzienny raport obecności    | Tak (manager) |
| `GET`  | `/api/attendance/manager/users/`                      | Lista pracowników           | Tak (manager) |
| `GET`  | `/api/attendance/manager/users/<id>/`                 | Szczegóły pracownika        | Tak (manager) |
| `GET`  | `/api/attendance/manager/users/<id>/sessions/`        | Sesje pracownika            | Tak (manager) |
| `GET`  | `/api/attendance/manager/users/<id>/daily-breakdown/` | Dzienny rozkład czasu pracy | Tak (manager) |

## Przykłady użycia

Logowanie:

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Generowanie tokenu QR:

```bash
curl -X POST http://localhost:8000/api/attendance/generate_qrcode/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"entry"}'
```

Weryfikacja tokenu QR (skan przez IoT):

```bash
curl -X POST http://localhost:8000/api/attendance/verify/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"<token>"}'
```

Sprawdzenie statusu skanu:

```bash
curl "http://localhost:8000/api/attendance/scan-status/?qr_token=<token>" \
  -H "Authorization: Bearer <access_token>"
# {"status":"pending","scanned":false,"event_type":"entry","scanned_at":null}
# {"status":"ok","scanned":true,"event_type":"entry","scanned_at":"2026-03-13T18:00:00Z"}
```

## Przydatne komendy

Domyślne konto admina (ładowane automatycznie z fixture przy starcie):

- login: `admin`
- hasło: `admin123`

Ręczne tworzenie superusera:

```bash
docker compose exec app python api/manage.py createsuperuser
```

Zatrzymanie i usunięcie kontenerów wraz z wolumenami:

```bash
docker compose down -v
```
