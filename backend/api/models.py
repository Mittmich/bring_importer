"""Pydantic request/response models shared by the routers."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class User(BaseModel):
    email: EmailStr
    password: str


class UserInDB(User):
    hashed_password: str


class RecipeCreate(BaseModel):
    image: str  # Base64 encoded image


class RecipeResponse(BaseModel):
    uuid: str
    url: str


class RecipeUpdate(BaseModel):
    """Body for ``PUT /recipes/{uuid}`` — the editor's editable surface."""

    title: Optional[str] = None
    recipeIngredient: Optional[List[str]] = None
    recipeInstructions: Optional[List[str]] = None
    recipeYield: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None
    html_content: Optional[str] = None


class Recipe(BaseModel):
    title: str
    recipeIngredient: List[str]
    recipeInstructions: Optional[List[str]] = None
    recipeYield: str = "4 servings"
    datePublished: Optional[str] = None
    description: Optional[str] = None
    html_content: Optional[str] = None
