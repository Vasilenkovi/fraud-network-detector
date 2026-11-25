# Интеграция API рабочего места аналитика

## Что добавлено

- Django app `api`: модели инцидентов, аудит решений и журнал Replay.
- DRF endpoints под `/api/`, закрытые `IsAuthenticated` + `SessionAuthentication`.
- Celery task для повторного rule-based анализа с Redis broker.
- Повторно используемый детектор `events/fraud_detection.py`; CLI-команда `analyze_fraud` теперь сохраняет найденные инциденты в PostgreSQL.
- Получение ограниченного подграфа из Neo4j через существующий `Neo4jGraphClient`.
- Вход аналитика по `/accounts/login/` и администрирование через `/admin/`.
- Обновлённый контракт `schemes/api_contract_v1.1.yaml`.

## Запуск (Django и Celery выполняются на хосте)

1. Установить зависимости: `pip install -r requirements.txt`.
2. Добавить в `.env` переменные из `.env.example`, в частности `REDIS_URL=redis://localhost:6379/0` и `CELERY_RESULT_BACKEND=redis://localhost:6379/1`.
3. Запустить инфраструктуру: `docker compose up -d postgres kafka neo4j redis`.
4. Применить миграции: `python manage.py migrate`.
5. Создать учётную запись: `python manage.py createsuperuser`.
6. Запустить Django: `python manage.py runserver 0.0.0.0:8000`.
7. В отдельном терминале запустить worker: `celery -A config worker -l info`.
8. Запустить существующий Kafka consumer, затем `python manage.py analyze_fraud` для первичного наполнения очереди инцидентов.

## API

- `GET /api/alerts/?status=new&limit=50&offset=0`
- `GET /api/alerts/AL-.../`
- `POST /api/alerts/AL-.../decision/` с JSON `{ "status": "confirmed", "comment": "..." }`
- `POST /api/replay/` с `start_time` и `end_time` в ISO 8601
- `GET /api/replay/{task_id}/` для проверки статуса Replay

Все API-вызовы требуют действующую Django-сессию. Для POST из браузера обязательно передавать CSRF-токен в `X-CSRFToken`.

## Важные ограничения текущей версии

- `risk_score` хранится как NULL: формула калиброванной rule-based оценки и ML-модель ещё не определены. UI должен показывать «не рассчитан», а не подменять это выдуманным числом.
- Replay повторно анализирует события, попавшие внутрь выбранного интервала. Если нужно выявлять цепочки, пересекающие границы периода, потребуется добавить временное окно контекста.
- Результаты детекции идемпотентно обновляют инцидент по fingerprint; уже принятый статус аналитика не сбрасывается.
- API-список использует пагинационный объект `{count, limit, offset, results}`; исходная схема с массивом уточнена в версии 1.1.
- Это интеграционный слой для текущего учебного проекта; перед production потребуются настройки секретов, HTTPS, ограничения доступа, аудит, rate limiting и мониторинг очереди.
