# Продакшен: Docker, Nginx, CI/CD, мониторинг, доступ к БД

Дополняет корневой **[README.md](../README.md)** (архитектура бота, webhook, health, безопасность, бэкапы). Здесь — выкладка на VPS, compose, Nginx, CI/CD и операции.

Этот документ **заменяет устаревшие шаблоны** вроде «python-telegram-bot + `main.py`»: в **law-bot** используются **aiogram 3**, **maxapi**, точка входа **`python -m src.main`**, вебхуки уже реализованы в коде (`TelegramMessenger`, `MaxMessenger`).

## Структура продакшен-стека

Файл **`docker-compose.prod.yml`** поднимает одну сеть **`legal_bot_network`**:

| Сервис | Назначение |
|--------|------------|
| **postgres** | PostgreSQL 15, volume `postgres_data` |
| **bot** | Приложение: вебхуки Telegram/MAX, FastAPI (**`API_ENABLED=true`** по умолчанию) |
| **nginx** | TLS и reverse proxy на публичный домен |
| **uptime-kuma** | **Обязательный** визуальный мониторинг доступности (дашборды, уведомления) |
| **adminer** (профиль **`db-ui`**) | Опциональный веб-UI для PostgreSQL на localhost |

Порты **Postgres**, **Uptime Kuma** и **Adminer** пробрасываются только на **`127.0.0.1`** на хосте VPS — не торчат в интернет без SSH/Nginx.

## Что исправлено относительно «сырых» шаблонов

| Неверно в шаблоне | Фактически в репозитории |
|-------------------|--------------------------|
| Библиотека `python-telegram-bot` | **aiogram 3** |
| Файл `main.py` в корне | **`src/main.py`**, запуск `python -m src.main` |
| Один порт вебхука | **Два HTTP-сервера**: Telegram (**8443**), MAX (**8444**), FastAPI (**8080**) |
| `BOT_TOKEN` / один URL | **`TELEGRAM_BOT_TOKEN`**, **`WEBHOOK_URL`**, **`TELEGRAM_WEBHOOK_PATH`**, отдельно **MAX** (`MAX_WEBHOOK_*`) |
| Нет миграций | При старте контейнера: **`alembic upgrade head`** (`scripts/docker-entrypoint.sh`) |

## Архитектура HTTP

- **Nginx** (TLS) проксирует снаружи:
  - путь Telegram webhook → контейнер бота **:8443**;
  - путь MAX webhook → **:8444**;
  - **`/v1/`** → **:8080** (интеграционное API: CRM, **единая** readiness без привязки к мессенджеру);
  - при **`API_DOCS_ENABLED=True`** — ещё **`/docs`**, **`/redoc`**, **`/openapi.json`** на **:8080** (в проде по умолчанию документация скрыта, см. README).
- Публичные URL для `setWebhook` / `subscribe_webhook` должны совпадать с **`build_telegram_webhook_url()`** и **`build_max_webhook_url()`** в `src/config/settings.py`.

### Health на портах webhook (Telegram и MAX)

Один модуль **`src/messengers/webhook_health.py`** регистрирует на каждом aiohttp-приложении мессенджера **`GET /health/live`** и **`GET /health/ready`**. Ответ **`/health/ready`** строится через **`run_ready_checks()`** (БД, бэкапы при **`BACKUP_ENABLED`**) — тот же состав **`checks`**, что и у **`GET /v1/health/ready`**, плюс поле **`service`**: **`telegram_webhook`** или **`max_webhook`**.

В шаблоне **`deploy/nginx/conf.d/law-bot.conf.example`** для MAX добавлены внешние пути **`/max/health/live`** и **`/max/health/ready`**, проксирующие на внутренние **`/health/...`** порта **8444**, чтобы на одном домене не конфликтовать с Telegram. Для Telegram при необходимости проксируйте **`/health/live`** и **`/health/ready`** на **:8443**. Универсальная проверка без привязки к порту мессенджера: **`https://<домен>/v1/health/ready`** (порт API **8080**).

## Мониторинг на проде (обязателен)

### 1. Проверки здоровья приложения

| URL (через Nginx, HTTPS) | Назначение |
|--------------------------|------------|
| **`GET /v1/health/live`** | Liveness, без БД |
| **`GET /v1/health/ready`** | Readiness: БД и при включённых бэкапах — **`checks.backup`**; **`503`** при сбое любой проверки |

Рекомендуется задать **`INTEGRATION_API_TOKEN`** и ограничить доступ к **`/v1/`** (Nginx: basic auth или allowlist IP), если API доступно из интернета. Документация Swagger (**`/docs`**) в продакшене по умолчанию отключена (**`API_DOCS_ENABLED`**, см. README, раздел «Безопасность»).

Дополнительно на портах webhook (см. выше): **`GET /health/live`**, **`GET /health/ready`** (поле **`service`** указывает мессенджер).

### 2. Uptime Kuma (включён в `docker-compose.prod.yml`)

После `docker compose -f docker-compose.prod.yml up -d` веб-интерфейс Kuma доступен **на самом VPS** по адресу **`http://127.0.0.1:3001`** (порт задаётся **`UPTIME_KUMA_PORT`** в `.env`).

**Первый вход:** создайте учётную запись администратора в мастере Kuma.

**Рекомендуемые мониторы (Monitors → Add):**

1. **HTTP(s)** — URL изнутри Docker: **`http://bot:8080/v1/health/ready`**  
   - Имя хоста **`bot`** резолвится внутри сети compose; проверяет API, БД и при **`BACKUP_ENABLED=True`** — цепочку бэкапов (поле **`checks.backup`** в ответе).
2. **HTTP(s)** — публичный URL: **`https://<ваш-домен>/v1/health/ready`**  
   - Проверяет полный путь TLS → Nginx → бот (как видит внешний мир).
3. Опционально — отдельный монитор на корень сайта или на webhook path (ожидаемые коды настраиваются в Kuma).

Уведомления (Telegram, e-mail и др.) настраиваются в Kuma (**Settings → Notifications**).

### 3. Удалённый доступ к UI Kuma с вашего ПК

Kuma не обязана быть в открытом интернете. Удобный способ — **SSH-туннель**:

```bash
ssh -L 3001:127.0.0.1:3001 user@<VPS_IP>
```

На локальной машине откройте **`http://127.0.0.1:3001`**. Альтернатива — отдельный поддомен за Nginx с HTTP Basic Auth и поддержкой WebSocket (сложнее; для большинства достаточно SSH).

## Удалённый доступ к PostgreSQL «визуально»

### Вариант A (рекомендуется): SSH-туннель + DBeaver / pgAdmin / DataGrip

На VPS Postgres слушает **`127.0.0.1:<POSTGRES_HOST_PORT>`** (по умолчанию **5432**) только на хосте.

С локального компьютера:

```bash
ssh -L 5433:127.0.0.1:5432 user@<VPS_IP>
```

В клиенте БД подключайтесь к **`localhost`**, порт **`5433`**, пользователь/пароль/БД — как в `.env` (`DB_USER`, `DB_PASSWORD`, `DB_NAME`).

Так вы смотрите таблицы, заявки и пользователей без открытия Postgres в интернет.

### Вариант B: Adminer (веб-UI на сервере)

Поднять только при необходимости:

```bash
docker compose -f docker-compose.prod.yml --profile db-ui up -d adminer
```

Интерфейс: **`http://127.0.0.1:8888`** на VPS (порт **`ADMINER_HOST_PORT`**). Удалённо — снова через SSH-туннель:

```bash
ssh -L 8888:127.0.0.1:8888 user@<VPS_IP>
```

Откройте **`http://127.0.0.1:8888`**, сервер: **`postgres`**, логин/пароль из `.env`.

**Не** выставляйте Adminer и Kuma на `0.0.0.0` без reverse proxy, пароля и firewall.

## Быстрый старт на сервере

1. Клонировать репозиторий.
2. `cp env.example .env`, заполнить токены, **`DB_PASSWORD`**, вебхуки, **`CERTBOT_EMAIL`** / **`CERTBOT_DOMAIN`**, **`BOT_IMAGE_REF`** (если образ из GHCR).
3. Конфиг Nginx: для MAX уже готов `deploy/nginx/conf.d/max.conf`; для Telegram/API возьмите шаблон `law-bot.conf.example` → `law-bot.conf`, подставьте `server_name`.
4. Сертификаты: **`bash scripts/init-letsencrypt.sh`** — автоматически выпускает Let's Encrypt и кладёт `fullchain.pem` / `privkey.pem` в `deploy/ssl/` (см. раздел [TLS](#tls-автоматический-выпуск-и-продление-lets-encrypt)).
5. `docker compose -f docker-compose.prod.yml up -d --build`.

Локальная сборка без registry: **`BOT_IMAGE_REF`** можно не задавать (сборка из `Dockerfile`).

## Пошаговый алгоритм: VPS, DNS и вебхуки

Ниже — полная цепочка того, что обычно делают один раз при выкладке. Остальные разделы документа (Nginx, health, Kuma) дополняют её деталями.

1. **VPS** с публичным IPv4 (или v6, если и DNS, и Telegram/MAX готовы работать с ним). Установите **Docker** и **Docker Compose** (plugin `docker compose`), см. официальную документацию Docker для вашего дистрибутива.
2. **Firewall**: открыть входящие **22** (SSH), **80** и **443** (HTTP/HTTPS для Nginx и выпуска сертификата). База, Kuma и Adminer в `docker-compose.prod.yml` слушают только **127.0.0.1** — наружу их не открывайте.
3. **DNS**: запись **A** (при необходимости **AAAA**) имени бота (например `bot.example.com`) на IP VPS. Публичный URL вебхука должен совпадать с этим именем и с **`server_name`** в Nginx.
4. **Репозиторий на сервере**: `git clone`, рабочий каталог — тот, где лежат `docker-compose.prod.yml` и `deploy/`.
5. **`.env` из `env.example`**: обязательно **`DB_PASSWORD`**, **`TELEGRAM_BOT_TOKEN`**. Для продакшена с вебхуками:
   - **`TELEGRAM_USE_WEBHOOK=true`**
   - **`WEBHOOK_URL=https://<ваш-домен>`** — тот же origin, что и у Nginx (без конфликта с логикой `build_telegram_webhook_url()` в `src/config/settings.py`: если в URL уже есть путь, он используется целиком; иначе к origin добавляется **`TELEGRAM_WEBHOOK_PATH`**).
   - **`TELEGRAM_WEBHOOK_PATH`** (по умолчанию **`/webhook`**) — **должен совпадать** с `location` в Nginx (см. `deploy/nginx/conf.d/law-bot.conf.example`).
   - Рекомендуется задать **`TELEGRAM_WEBHOOK_SECRET`** (заголовок `X-Telegram-Bot-Api-Secret-Token` проксируется в примере Nginx).
   - Для MAX: **`MAX_USE_WEBHOOK=true`**, **`MAX_BOT_TOKEN`**, **`MAX_WEBHOOK_URL`**, **`MAX_WEBHOOK_PATH`** (по умолчанию **`/max/webhook`**) и **`MAX_WEBHOOK_SECRET`** — согласовать с `location` в Nginx и с заголовком в примере конфига.
   - При образе из GHCR: **`BOT_IMAGE_REF=ghcr.io/...`** (см. блок в конце `env.example`).
6. **Nginx**: `law-bot.conf.example` → `law-bot.conf` в `deploy/nginx/conf.d/`, подставить **`server_name`**, смонтировать каталог с **TLS** в `deploy/ssl/` (`fullchain.pem`, `privkey.pem` — пути как в примере).
7. **TLS**: `bash scripts/init-letsencrypt.sh` — автоматический выпуск Let's Encrypt (webroot) с копированием PEM в `deploy/ssl/` и последующим авто-продлением сервисом `certbot` (см. раздел [TLS](#tls-автоматический-выпуск-и-продление-lets-encrypt)). Альтернатива — **Caddy** с авто-HTTPS вместо Nginx.
8. **Запуск**: `docker compose -f docker-compose.prod.yml up -d` (при необходимости `--build`). Дождаться **`healthy`** у сервиса **`bot`** (health на **`http://127.0.0.1:8080/v1/health/live`** внутри контейнера).
9. **Регистрация вебхуков у Telegram и MAX**: отдельно вызывать API вручную **не обязательно** — при старте приложение поднимает aiohttp на **8443** (Telegram) и **8444** (MAX) и вызывает **`set_webhook`** / подписку MAX с URL из **`build_telegram_webhook_url()`** и **`build_max_webhook_url()`** (см. `TelegramMessenger._start_webhook` и MAX-мессенджер). Убедитесь по логам `docker compose -f docker-compose.prod.yml logs -f bot`, что указан ожидаемый публичный URL и нет ошибок API.
10. **Проверка снаружи**: `curl` к **`https://<домен>/v1/health/ready`** и при необходимости к путям health вебхуков (см. раздел «Проверка после деплоя»).

Если путь или домен в `.env` меняются, после правки обычно достаточно **перезапустить контейнер бота**, чтобы перерегистрировать вебхук.

## TLS (автоматический выпуск и продление Let's Encrypt)

`docker-compose.prod.yml` включает сервис **`certbot`** и каталог `deploy/ssl/`, куда попадают сертификаты. Отдельно ставить certbot на хост и запускать `certbot --nginx` **не нужно** — плагин `--nginx` управляет nginx на самом хосте, а здесь nginx работает в контейнере. Используется схема **webroot** через контейнерный nginx.

Как это устроено:

- В `deploy/nginx/conf.d/max.conf` блок `listen 80` отдаёт `/.well-known/acme-challenge/` из `/var/www/certbot` (volume `certbot_www`), остальное редиректит на HTTPS.
- nginx читает сертификат из `/etc/nginx/ssl` (смонтирован `deploy/ssl`).
- Сервис `certbot` периодически делает `certbot renew` и через `--deploy-hook` копирует свежие `fullchain.pem` / `privkey.pem` в `deploy/ssl`; nginx раз в 6 часов перечитывает их (`nginx -s reload`).

### Первый выпуск

1. В `.env` задайте **`CERTBOT_EMAIL`** (и при необходимости **`CERTBOT_DOMAIN`**, по умолчанию `max.demyanovblog.ru`).
2. Убедитесь, что DNS-запись **A** домена указывает на VPS и открыты порты **80** и **443**.
3. Из каталога с `docker-compose.prod.yml` запустите:

```bash
bash scripts/init-letsencrypt.sh
```

Скрипт создаёт временный самоподписанный сертификат (чтобы nginx стартовал с блоком 443), поднимает nginx, получает боевой сертификат через webroot, копирует PEM в `deploy/ssl/` и перезагружает nginx. Тестовый прогон без расхода лимита: `CERTBOT_STAGING=1 bash scripts/init-letsencrypt.sh`.

4. Поднимите весь стек:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Продление дальше автоматическое (сервис `certbot`). Проверить вручную: `docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot certificates`.

### Альтернатива

**Caddy** — авто-HTTPS «из коробки»; может заменить связку nginx + certbot.

## Развёртывание только MAX (домен `max.demyanovblog.ru`)

Если на этом домене работает **только** бот MAX (без Telegram и публичного API), порядок такой:

1. **VPS**: установлен Docker + Docker Compose; открыты порты **22**, **80**, **443**; DNS **A** `max.demyanovblog.ru` → IP сервера.
2. **Репозиторий**: `git clone`, перейдите в каталог с `docker-compose.prod.yml`.
3. **`.env`** (`cp env.example .env`), минимум:
   - `DB_PASSWORD=<надёжный пароль>`
   - `MAX_BOT_TOKEN=<токен MAX>`
   - `MAX_USE_WEBHOOK=true`
   - `MAX_WEBHOOK_URL=https://max.demyanovblog.ru` (путь допишется из `MAX_WEBHOOK_PATH`)
   - `MAX_WEBHOOK_PATH=/max/webhook`
   - `MAX_WEBHOOK_SECRET=<длинная случайная строка>`
   - `CERTBOT_EMAIL=<ваш e-mail>`, `CERTBOT_DOMAIN=max.demyanovblog.ru`
   - **`TELEGRAM_BOT_TOKEN`** оставьте **пустым** — тогда Telegram-мессенджер не запускается (см. `src/main.py`), поднимется только MAX.
4. **TLS**: `bash scripts/init-letsencrypt.sh` (см. раздел TLS выше).
5. **Запуск**: `docker compose -f docker-compose.prod.yml up -d` (при локальной сборке добавьте `--build`).
6. **Проверка**: дождитесь `healthy` у сервиса `bot`, затем:

```bash
curl -fsS https://max.demyanovblog.ru/max/health/ready
docker compose -f docker-compose.prod.yml logs -f bot   # строка про MAX webhook и публичный URL
```

Бот при старте сам вызывает `subscribe_webhook` с URL из `build_max_webhook_url()` — отдельно регистрировать webhook не нужно. После смены `MAX_WEBHOOK_*` достаточно перезапустить контейнер `bot`.

## CI/CD: ветка `release`

Workflow **`.github/workflows/release-deploy.yml`**: образ в **GHCR**, опционально SSH-деплой при **`SSH_DEPLOY_ENABLED=true`**.

| Secret | Назначение |
|--------|------------|
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH` | SSH на VPS |
| `GHCR_PULL_TOKEN` | При **приватном** образе GHCR |

## Проверка после деплоя

```bash
curl -fsS https://<domain>/v1/health/live
curl -fsS https://<domain>/v1/health/ready
# Если в Nginx настроены пути к health на портах webhook:
# curl -fsS https://<domain>/max/health/ready
docker compose -f docker-compose.prod.yml logs -f bot
```

## Безопасность (кратко для продакшена)

См. раздел **[Безопасность](../README.md#безопасность)** в **README.md**: токен интеграционного API, отключение Swagger в проде, SSRF для исходящего webhook, заголовки HTTP у API. На сервере комбинируйте **`INTEGRATION_API_TOKEN`**, Nginx (TLS, ограничение доступа к **`/v1/`**), SSH для Kuma и БД.

## Файлы в репозитории

| Файл | Назначение |
|------|------------|
| `Dockerfile` | Образ Python 3.12, entrypoint с миграциями |
| `docker-compose.yml` | Разработка: бот + Postgres |
| `docker-compose.prod.yml` | Продакшен: Postgres, бот, Nginx, **Uptime Kuma**, опционально Adminer |
| `deploy/nginx/conf.d/law-bot.conf.example` | Шаблон reverse proxy (webhook Telegram/MAX, API, **`/max/health/*`**) |
| `deploy/nginx/conf.d/max.conf` | Готовый конфиг для MAX-домена (ACME-челлендж, HTTPS, `/max/webhook`, health) |
| `scripts/init-letsencrypt.sh` | Первый выпуск TLS-сертификата Let's Encrypt в `deploy/ssl/` |
| `src/messengers/webhook_health.py` | Общие **`/health/live`** и **`/health/ready`** для webhook Telegram и MAX |
| `scripts/docker-entrypoint.sh` | `alembic upgrade head`, затем запуск бота |
| `.github/workflows/release-deploy.yml` | Ветка **release**: образ GHCR, опциональный SSH-деплой |
