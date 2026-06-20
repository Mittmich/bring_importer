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


class Ingredient(BaseModel):
    amount: str  # "2 cups", "200 g", "" for "to taste"
    name: str


class InstructionStep(BaseModel):
    text: str
    ingredients: List[int] = []  # zero-based indices into Recipe.ingredients


class Recipe(BaseModel):
    title: str
    ingredients: List[Ingredient]
    instructions: List[InstructionStep] = []
    recipeYield: str = "4 servings"
    datePublished: Optional[str] = None
    description: Optional[str] = None


class RecipeUpdate(BaseModel):
    """Body for ``PUT /recipes/{uuid}`` — the editor's editable surface."""

    title: Optional[str] = None
    ingredients: Optional[List[Ingredient]] = None
    instructions: Optional[List[InstructionStep]] = None
    recipeYield: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None
    is_public: Optional[bool] = None
