import getpass
import sys
from pathlib import Path

from pymongo import ReturnDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.mongodb import admins_collection
from app.security.auth_utils import hash_password


def reset_admin_password(email: str, new_password: str) -> bool:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Admin email is required.")
    if len(new_password) < 12:
        raise ValueError("Use a password with at least 12 characters.")

    updated_admin = admins_collection.find_one_and_update(
        {
            "email": normalized_email,
            "is_active": {"$ne": False},
        },
        {"$set": {"password_hash": hash_password(new_password)}},
        projection={"_id": 1},
        return_document=ReturnDocument.AFTER,
    )
    return updated_admin is not None


def main() -> None:
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("New admin password: ")
    confirm_password = getpass.getpass("Confirm new password: ")

    if password != confirm_password:
        raise SystemExit("Passwords do not match.")

    if reset_admin_password(email, password):
        print("Admin password reset successfully.")
    else:
        raise SystemExit("No active admin account found for that email.")


if __name__ == "__main__":
    main()
