from fastapi import HTTPException, status

from app.database.mongodb import admins_collection
from app.security.auth_utils import create_access_token, verify_password


def login_admin(email: str, password: str) -> dict:
    admin = admins_collection.find_one({"email": email.lower()})

    if not admin or not verify_password(password, admin["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(admin["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
    }
