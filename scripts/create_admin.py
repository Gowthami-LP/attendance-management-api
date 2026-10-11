import getpass

from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import admins_collection, create_admin_indexes
from app.security.auth_utils import hash_password

load_dotenv()


def main():
    create_admin_indexes()

    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password: ")
    confirm_password = getpass.getpass("Confirm password: ")

    if not email or not password:
        print("Email and password are required.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    if len(password) < 12:
        print("Use a password with at least 12 characters.")
        return

    admin = {
        "email": email,
        "password_hash": hash_password(password),
        "role": "admin",
        "is_active": True,
    }

    try:
        admins_collection.insert_one(admin)
        print("Admin account created successfully.")
    except DuplicateKeyError:
        print("An admin account with this email already exists.")


if __name__ == "__main__":
    main()
