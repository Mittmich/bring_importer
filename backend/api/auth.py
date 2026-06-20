"""Authentication helpers: password hashing, JWT, current-user resolution.

The router in ``api/routers/auth.py`` exposes ``POST /token`` (login).
The dependency ``get_current_user`` is reused by ``api/routers/recipes.py``
to gate mutating endpoints.
"""

from datetime import datetime, timedelta
from typing import Optional

import jwt
import passlib.exc
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from api.config import ALGORITHM, SECRET_KEY
from api.db import get_db_connection
from api.models import UserInDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    """Return True iff ``plain_password`` matches ``hashed_password``.

    Tolerant of unknown hash formats: ``passlib.exc.UnknownHashError`` is
    caught and treated as "no match" so users migrated from a different
    auth system don't 500 the auth check just because their stored hash
    isn't a bcrypt.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except passlib.exc.UnknownHashError:
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def get_user(email: str) -> Optional[UserInDB]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return UserInDB(email=user["email"], password="", hashed_password=user["hashed_password"])
    return None


def authenticate_user(email: str, password: str):
    user = get_user(email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError as err:
        raise credentials_exception from err
    user = get_user(email=email)
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[UserInDB]:
    """Like ``get_current_user`` but returns ``None`` instead of raising 401."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        if email is None:
            return None
    except jwt.PyJWTError:
        return None
    return get_user(email=email)


def get_user_id(email: str) -> Optional[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return int(result["id"])
    return None
