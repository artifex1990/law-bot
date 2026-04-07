"""Валидация пользовательских данных (RU сегмент)."""

import re

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]*"
    r"@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$"
)

_RU_MOBILE_RE = re.compile(
    r"^(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$"
)

_RU_LANDLINE_RE = re.compile(
    r"^(\+7|8)[\s\-]?\(?\d{3,5}\)?[\s\-]?\d{1,3}[\s\-]?\d{2}[\s\-]?\d{2}$"
)

_NON_DIGIT = re.compile(r"\D")


def validate_email(email: str) -> bool:
    """Проверить email-адрес."""
    email = email.strip()
    if not email or len(email) > 254:
        return False
    return bool(_EMAIL_RE.match(email))


_RU_STARTS = re.compile(r"^(\+7|8)")


def validate_ru_phone(phone: str) -> bool:
    """Проверить телефон РФ (+7/8, мобильные и стационарные)."""
    phone = phone.strip()
    if not phone:
        return False
    if _RU_MOBILE_RE.match(phone):
        return True
    if _RU_LANDLINE_RE.match(phone):
        return True
    digits = _NON_DIGIT.sub("", phone)
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return True
    if len(digits) == 10 and _RU_STARTS.match(phone):
        return True
    return len(digits) == 10 and not phone.startswith("+")


def normalize_ru_phone(phone: str) -> str | None:
    """Нормализовать телефон РФ в формат +7XXXXXXXXXX.

    Возвращает None если телефон невалиден.
    """
    if not validate_ru_phone(phone):
        return None
    digits = _NON_DIGIT.sub("", phone)
    if len(digits) == 10:
        return f"+7{digits}"
    if len(digits) == 11:
        return f"+7{digits[1:]}"
    return None


def format_validation_error(
    phone_ok: bool,
    email_ok: bool,
) -> str | None:
    """Сформировать сообщение об ошибке валидации."""
    errors: list[str] = []
    if not phone_ok:
        errors.append(
            "Телефон должен быть в формате РФ: "
            "+7XXXXXXXXXX, 8XXXXXXXXXX "
            "или стационарный."
        )
    if not email_ok:
        errors.append("Email указан в неверном формате.")
    if errors:
        return "\n".join(errors)
    return None
