from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from typing import List

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Fetch the authenticated user's profile and preferences."""
    return current_user

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences (e.g. full_name)."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
