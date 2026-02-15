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

## Przydatne komendy

Tworzenie superusera:

```bash
docker compose exec app python api/manage.py createsuperuser
```

Zatrzymanie i usunięcie kontenerów + wolumenów:

```bash
docker compose down -v
```
