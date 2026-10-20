import pytest

from app.security.auth_utils import verify_password
from scripts import reset_admin_password as reset_script


def test_reset_admin_password_updates_active_account(fake_collection, monkeypatch):
    admins = fake_collection(
        [
            {
                "email": "lpgtechnologies@gmail.com",
                "password_hash": "old-hash",
                "is_active": True,
            }
        ]
    )
    monkeypatch.setattr(reset_script, "admins_collection", admins)

    assert reset_script.reset_admin_password(
        " LPGTechnologies@gmail.com ",
        "A-new-safe-password-123",
    )
    assert verify_password(
        "A-new-safe-password-123",
        admins.documents[0]["password_hash"],
    )


def test_reset_admin_password_rejects_missing_or_inactive_account(
    fake_collection,
    monkeypatch,
):
    admins = fake_collection(
        [
            {
                "email": "inactive@example.com",
                "password_hash": "old-hash",
                "is_active": False,
            }
        ]
    )
    monkeypatch.setattr(reset_script, "admins_collection", admins)

    assert not reset_script.reset_admin_password(
        "inactive@example.com",
        "A-new-safe-password-123",
    )
    assert not reset_script.reset_admin_password(
        "missing@example.com",
        "A-new-safe-password-123",
    )


def test_reset_admin_password_requires_minimum_length():
    with pytest.raises(ValueError, match="at least 12 characters"):
        reset_script.reset_admin_password("admin@example.com", "short")
