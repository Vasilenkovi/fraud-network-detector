# Fraud Graph — Anti-Fraud

Учебный проект для выявления подозрительных групп клиентов и счетов по графу связей.

## Возможности текущей версии

- Генерация тестовых событий и трёх сценариев: `shared_device`, `fast_chain`, `cycle_transfer`.
- Публикация событий в Kafka.
- Валидация входящих событий и пакетная запись в PostgreSQL.
- Синхронизация клиентов, счетов, устройств и переводов в Neo4j.
- Rule-based обнаружение подозрительных групп командой `analyze_fraud`.
- REST API для просмотра инцидентов, фиксации решений аналитика и запуска Replay.
- Celery + Redis для асинхронных задач Replay.

> Это инструкция для локальной разработки. Конфигурация DGX Spark / Linux ARM64 пока не проходила отдельное аппаратное тестирование.

## 1. Требования

- Git
- Docker Desktop (Windows/macOS) или Docker Engine + Docker Compose plugin (Linux)
- Python 3.12
- Доступные локальные порты: `5432`, `6379`, `7474`, `7687`, `9092`, `8000`

Все Python-процессы запускаются на хосте, а PostgreSQL, Kafka, Neo4j и Redis — в Docker.

## 2. Получение проекта

```bash
git clone <URL-репозитория>
cd fg
```

Если репозиторий уже клонирован, перейдите в каталог проекта.

## 3. Настройка окружения

Скопируйте пример переменных окружения.

**Windows PowerShell:**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Для локального запуска значения из `.env.example` подходят как стартовые. При необходимости измените `DJANGO_SECRET_KEY` и пароли. Не коммитьте `.env`.

Основные параметры:
- PostgreSQL: `POSTGRES_*`
- Kafka: `KAFKA_*`
- Neo4j: `NEO4J_*`
- Redis / Celery: `REDIS_URL`, `CELERY_RESULT_BACKEND`

При запуске Python на хосте адреса сервисов должны указывать на `localhost`. Не заменяйте их на имена Compose-сервисов (`postgres`, `kafka` и т. п.), если приложение по-прежнему запускается вне Docker.

## 4. Запуск инфраструктуры

```bash
docker compose up -d
docker compose ps
```

Дождитесь, пока PostgreSQL и Redis перейдут в состояние `healthy`. Kafka и Neo4j должны иметь статус `Up`.

Веб-интерфейсы:
- Neo4j Browser: http://localhost:7474
- Django: http://127.0.0.1:8000/admin/

Neo4j для локальной конфигурации:
- пользователь: `neo4j`
- пароль: `fraudgraph123` (если не меняли `.env`)

## 5. Установка Python-зависимостей

Создайте виртуальное окружение.

**Windows PowerShell:**
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Если PowerShell запрещает запуск скрипта активации, выполните для текущего окна:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Подготовка Django

Из корня проекта и при активированном `.venv`:

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
```

Создание суперпользователя требуется для входа в Django Admin и API, защищённый сессионной аутентификацией.

## 7. Запуск приложения

Каждый постоянно работающий процесс запускайте в отдельном терминале. В каждом терминале перейдите в каталог проекта и активируйте `.venv`.

### Терминал 1 — Django

```bash
python manage.py runserver
```

Админ-панель: http://127.0.0.1:8000/admin/

### Терминал 2 — Celery Worker

Celery нужен для асинхронного Replay.

**Windows:**
```powershell
celery -A config worker -l info --pool=solo
```

`--pool=solo` отключает prefork-мультипроцессность, которая может завершаться ошибкой `WinError 5` в Windows. Это режим локальной разработки, а не изменение кода задачи.

**Linux / macOS:**
```bash
celery -A config worker -l info
```

На Linux Celery использует стандартный пул `prefork`.

### Терминал 3 — Kafka Consumer

```bash
python manage.py consume_events
```

Consumer продолжает слушать топик `events`. Для штатной остановки нажмите `Ctrl+C`: текущая пачка должна быть обработана перед завершением.

### Терминал 4 — Генератор тестовых событий

```bash
python main.py
```

По умолчанию генератор работает 60 секунд, использует 20 клиентов и долю мошеннических сценариев 15%.

Параметры генератора:
```bash
python main.py --duration 60 --clients 20 --fraud-rate 0.15
```

Для непрерывной генерации:
```bash
python main.py --duration 0
```

Для повторяемой последовательности псевдослучайных данных:
```bash
python main.py --seed 42 --duration 60
```

После завершения генерации создаётся/обновляется `fraud_manifest.json` с описанием внедрённых сценариев.

### Терминал 5 — Анализ

После того как генератор завершился, а Consumer обработал накопившиеся сообщения (остановите Consumer через `Ctrl+C`), выполните:

```bash
python manage.py shell -c "from events.models import EventLog; print('Events:', EventLog.objects.count())"
python manage.py analyze_fraud
```

Команда `analyze_fraud` анализирует журнал событий PostgreSQL и сохраняет найденные группы в PostgreSQL.

Повторный запуск анализа не должен создавать новые копии уже известных групп при совпадающем fingerprint: существующие записи могут обновляться.

## 8. REST API

Все API-маршруты находятся под `/api/` и требуют аутентифицированную Django-сессию.

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/api/alerts/` | Список инцидентов |
| `GET` | `/api/alerts/{alert_id}/` | Детали инцидента и подграф Neo4j |
| `POST` | `/api/alerts/{alert_id}/decision/` | Решение аналитика: `confirmed` или `rejected` |
| `POST` | `/api/replay/` | Создать задачу Replay |
| `GET` | `/api/replay/{task_id}/` | Получить состояние задачи Replay |

Для работы с API войдите в Django Admin в браузере: http://127.0.0.1:8000/admin/ . API использует `SessionAuthentication`; для POST-запросов из браузера требуется CSRF-токен.

Параметры списка инцидентов:
- `status` — фильтр по статусу;
- `scheme` — фильтр по типу схемы;
- `limit` — размер страницы (1–200, по умолчанию 50);
- `offset` — смещение.

## 9. Проверка и тесты

```bash
python manage.py test
```

Быстрые проверки:
```bash
python manage.py check
python manage.py showmigrations
python manage.py shell -c "from events.models import EventLog; print(EventLog.objects.count())"
```

## 10. Остановка

Остановить Django, Celery, Consumer и генератор можно через `Ctrl+C` в соответствующих терминалах.

Остановить контейнеры, сохранив данные:
```bash
docker compose down
```

Удалить контейнеры **вместе со всеми данными PostgreSQL, Neo4j и Redis**:
```bash
docker compose down -v
```

> `down -v` — разрушительная команда. Не используйте её, если нужно сохранить данные проекта.

## 11. Совместимость с Linux ARM64 / NVIDIA DGX Spark

В проекте не зафиксирована архитектура `amd64` и не задано принудительное поле `platform` для Docker-образов. Docker выбирает подходящий вариант образа для архитектуры хоста, если издатель образа публикует multi-architecture manifest.

При переносе на DGX Spark необходимо отдельно проверить:
1. Архитектуру и версию ОС (`uname -m`, ожидается `aarch64` / `arm64`).
2. Наличие ARM64-вариантов используемых Docker-образов PostgreSQL, Kafka, Neo4j и Redis.
3. Установку Python-пакетов из `requirements.txt` на ARM64, в первую очередь `confluent-kafka` и `psycopg[binary]`.
4. Запуск Django, Consumer и Celery Worker.
5. Корректность доступа к GPU для будущих ML-компонентов — текущий rule-based модуль GPU не использует.

На DGX Spark (Linux ARM64) для Celery следует начать со стандартного запуска:
```bash
celery -A config worker -l info
```

Если какой-либо Python-пакет не предоставляет совместимый ARM64 wheel, потребуется установленный системный компилятор и development-зависимости либо отдельный ARM64-совместимый способ установки. Этот сценарий ещё не проверен на целевом устройстве.

## 12. Структура проекта

```text
fg/
├── api/                  # REST API, модели инцидентов, Replay task
├── config/               # настройки Django и Celery
├── events/               # события, Consumer, PostgreSQL sink, Neo4j, detection
├── schemes/              # схемы и документация
├── templates/             # Django templates
├── docker-compose.yml     # инфраструктура
├── main.py                # генератор тестовых событий
├── manage.py
├── requirements.txt
├── .env.example
└── fraud_manifest.json    # эталон внедрённых сценариев (генерируется main.py)
```

## Примечание по безопасности

Значения `.env.example` предназначены только для локальной разработки. Перед развёртыванием в общей или производственной среде задайте уникальные пароли, надёжный `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` и корректный список `DJANGO_ALLOWED_HOSTS`.
