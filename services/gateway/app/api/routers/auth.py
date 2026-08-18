import datetime
import uuid

import bcrypt
from fastapi import APIRouter, Depends

from services.gateway.app.api.dependencies.auth import (
    generate_jwt_token,
    verify_auth_token,
)
from services.gateway.app.schemas.auth import (
    TokenResponse,
    UserLogin,
    UserRegister,
)
from shared.database.mongodb import get_mongodb_database
from shared.exceptions.handlers import UnauthorizedException
from shared.schemas.responses import SuccessResponse


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=SuccessResponse[TokenResponse],
)
async def register_user(
    payload: UserRegister,
) -> SuccessResponse[TokenResponse]:
    db = get_mongodb_database()
    users_collection = db["users"]

    existing_user = await users_collection.find_one(
        {"email": payload.email}
    )

    if existing_user:
        raise UnauthorizedException(
            message="User with this email already exists"
        )

    hashed_pwd = bcrypt.hashpw(
        payload.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    user_id = f"usr_{uuid.uuid4().hex[:12]}"

    user_doc = {
        "id": user_id,
        "name": payload.name,
        "email": payload.email,
        "password_hash": hashed_pwd,
        "role": "user",
        "created_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
    }

    await users_collection.insert_one(user_doc)

    token = generate_jwt_token(
        user_id=user_id,
        role="user",
    )

    return SuccessResponse(
        data=TokenResponse(
            token=token,
            user_id=user_id,
            name=payload.name,
            email=payload.email,
            role="user",
        ),
        message="User registered successfully",
    )


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
)
async def login_user(
    payload: UserLogin,
) -> SuccessResponse[TokenResponse]:
    db = get_mongodb_database()
    users_collection = db["users"]

    user = await users_collection.find_one(
        {"email": payload.email}
    )

    if not user:
        raise UnauthorizedException(
            message="Invalid email or password"
        )

    stored_hash = user.get("password_hash", "")

    if (
        not stored_hash
        or not bcrypt.checkpw(
            payload.password.encode("utf-8"),
            stored_hash.encode("utf-8"),
        )
    ):
        raise UnauthorizedException(
            message="Invalid email or password"
        )

    token = generate_jwt_token(
        user_id=user["id"],
        role=user.get("role", "user"),
    )

    return SuccessResponse(
        data=TokenResponse(
            token=token,
            user_id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user.get("role", "user"),
        ),
        message="Login successful",
    )


@router.get(
    "/me",
    response_model=SuccessResponse[TokenResponse],
)
async def get_current_user(
    auth: dict = Depends(verify_auth_token),
) -> SuccessResponse[TokenResponse]:
    user_id = auth.get("user_id")

    if not user_id:
        raise UnauthorizedException(
            message="Authenticated user identity is missing"
        )

    db = get_mongodb_database()
    users_collection = db["users"]

    user = await users_collection.find_one(
        {"id": user_id}
    )

    if not user:
        raise UnauthorizedException(
            message="Authenticated user no longer exists"
        )

    return SuccessResponse(
        data=TokenResponse(
            token=auth["token"],
            user_id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user.get("role", "user"),
        ),
        message="Current user retrieved successfully",
    )