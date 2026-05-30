#!/usr/bin/env bash
# Первый выпуск TLS-сертификата Let's Encrypt для домена бота.
#
# Что делает скрипт:
#   1. создаёт временный самоподписанный сертификат (чтобы nginx стартовал с 443 ssl);
#   2. поднимает nginx — он отдаёт ACME-челлендж по /.well-known/acme-challenge/;
#   3. запускает certbot (webroot) и получает настоящий сертификат;
#   4. копирует fullchain.pem и privkey.pem в ./deploy/ssl;
#   5. перезагружает nginx с боевым сертификатом.
#
# Дальнейшее продление выполняет сервис certbot из docker-compose.prod.yml автоматически.
#
# Запуск на сервере (из каталога с docker-compose.prod.yml):
#   CERTBOT_EMAIL=you@example.com bash scripts/init-letsencrypt.sh
#
# Переменные можно задать в .env (CERTBOT_DOMAIN, CERTBOT_EMAIL) или в окружении.
# Тестовый прогон без расхода лимита Let's Encrypt: CERTBOT_STAGING=1

set -euo pipefail

# Подхватываем CERTBOT_* из .env БЕЗОПАСНО: читаем только нужные ключи,
# не исполняя файл как shell-скрипт (значения с запятыми/пробелами/решётками
# в .env иначе ломают `source`).
read_env_var() {
    local key="$1" line val
    [ -f .env ] || return 0
    line="$(grep -E "^[[:space:]]*${key}=" .env | tail -n 1)" || return 0
    [ -n "$line" ] || return 0
    val="${line#*=}"
    # снять окружающие кавычки (одинарные/двойные)
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    printf '%s' "$val"
}

# Приоритет: переменная окружения > значение из .env > дефолт
DOMAIN="${CERTBOT_DOMAIN:-$(read_env_var CERTBOT_DOMAIN)}"
DOMAIN="${DOMAIN:-max.demyanovblog.ru}"
EMAIL="${CERTBOT_EMAIL:-$(read_env_var CERTBOT_EMAIL)}"
SSL_DIR="./deploy/ssl"
COMPOSE="docker compose -f docker-compose.prod.yml"

if [ -z "$EMAIL" ]; then
    echo "ОШИБКА: задайте CERTBOT_EMAIL (в .env или в окружении)." >&2
    echo "Пример: CERTBOT_EMAIL=you@example.com bash scripts/init-letsencrypt.sh" >&2
    exit 1
fi

staging_arg=""
if [ "${CERTBOT_STAGING:-0}" != "0" ]; then
    staging_arg="--staging"
    echo ">> Режим STAGING (тестовый сертификат Let's Encrypt)"
fi

echo ">> Домен: $DOMAIN, e-mail: $EMAIL"
mkdir -p "$SSL_DIR"

# 1. Временный самоподписанный сертификат, чтобы nginx поднялся с блоком 443 ssl.
#    Используем хостовый openssl (есть почти везде); иначе — openssl из образа
#    certbot через --entrypoint (у образа entrypoint=certbot, нельзя звать `sh -c`).
if [ ! -s "$SSL_DIR/fullchain.pem" ]; then
    echo ">> Создаю временный самоподписанный сертификат..."
    if command -v openssl >/dev/null 2>&1; then
        openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
            -keyout "$SSL_DIR/privkey.pem" -out "$SSL_DIR/fullchain.pem" \
            -subj "/CN=$DOMAIN"
    else
        docker run --rm --entrypoint openssl \
            -v "$(pwd)/$SSL_DIR:/ssl" certbot/certbot \
            req -x509 -nodes -newkey rsa:2048 -days 1 \
            -keyout /ssl/privkey.pem -out /ssl/fullchain.pem -subj "/CN=$DOMAIN"
    fi
fi

# 2. Поднимаем nginx (он отдаёт ACME-челлендж на :80).
echo ">> Запускаю nginx..."
$COMPOSE up -d nginx

# 3. Получаем боевой сертификат через webroot и сразу копируем PEM в ./deploy/ssl.
echo ">> Запрашиваю сертификат Let's Encrypt..."
$COMPOSE run --rm --entrypoint certbot certbot \
    certonly --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email --non-interactive \
    --force-renewal $staging_arg \
    --deploy-hook "cp -L /etc/letsencrypt/live/$DOMAIN/fullchain.pem /ssl/fullchain.pem && cp -L /etc/letsencrypt/live/$DOMAIN/privkey.pem /ssl/privkey.pem"

# 4. Перезагружаем nginx с настоящим сертификатом.
echo ">> Перезагружаю nginx..."
$COMPOSE exec nginx nginx -s reload

echo ">> Готово. Сертификат для $DOMAIN установлен в $SSL_DIR."
echo ">> Поднимите весь стек: $COMPOSE up -d"
