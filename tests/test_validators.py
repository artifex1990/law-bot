"""Tests: RU phone and email validators."""

import pytest

from src.core.validators import (
    format_validation_error,
    normalize_ru_phone,
    validate_email,
    validate_ru_phone,
)

# ---- validate_ru_phone ----


@pytest.mark.parametrize(
    "phone",
    [
        "+79991234567",
        "89991234567",
        "+7 999 123 45 67",
        "+7(999)123-45-67",
        "8(495)1234567",
        "84951234567",
        "+7 495 123 45 67",
        "9991234567",
    ],
)
def test_valid_ru_phones(phone):
    assert validate_ru_phone(phone) is True


@pytest.mark.parametrize(
    "phone",
    [
        "",
        "123",
        "+1234567890",
        "abc",
        "+49301234567",
        "12345",
    ],
)
def test_invalid_ru_phones(phone):
    assert validate_ru_phone(phone) is False


# ---- normalize_ru_phone ----


def test_normalize_mobile_plus7():
    assert normalize_ru_phone("+79991234567") == "+79991234567"


def test_normalize_mobile_8():
    assert normalize_ru_phone("89991234567") == "+79991234567"


def test_normalize_10_digits():
    assert normalize_ru_phone("9991234567") == "+79991234567"


def test_normalize_with_spaces():
    assert normalize_ru_phone("+7 999 123 45 67") == "+79991234567"


def test_normalize_invalid():
    assert normalize_ru_phone("123") is None
    assert normalize_ru_phone("") is None


# ---- validate_email ----


@pytest.mark.parametrize(
    "email",
    [
        "user@example.com",
        "test.user@mail.ru",
        "a@b.co",
        "user+tag@gmail.com",
    ],
)
def test_valid_emails(email):
    assert validate_email(email) is True


@pytest.mark.parametrize(
    "email",
    [
        "",
        "not-email",
        "@example.com",
        "user@",
        "user@.com",
        "a" * 255 + "@b.com",
    ],
)
def test_invalid_emails(email):
    assert validate_email(email) is False


# ---- format_validation_error ----


def test_format_error_both_invalid():
    err = format_validation_error(False, False)
    assert err is not None
    assert "Телефон" in err
    assert "Email" in err


def test_format_error_phone_only():
    err = format_validation_error(False, True)
    assert err is not None
    assert "Телефон" in err


def test_format_error_all_valid():
    assert format_validation_error(True, True) is None
