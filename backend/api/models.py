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
    tags: Optional[List[str]] = None
    training_verified: Optional[bool] = None


class Tag(BaseModel):
    """A user-defined tag, with usage count and optional explicit colour.

    ``color`` is ``None`` when the user hasn't picked one; the frontend then
    derives a stable default from the name against its theme palette.
    """

    id: int
    name: str
    count: int
    color: Optional[str] = None


class TagUpdate(BaseModel):
    """Body for ``PATCH /recipes/tags/{id}`` — rename and/or recolour."""

    name: Optional[str] = None
    color: Optional[str] = None


class MealPlanEntryCreate(BaseModel):
    """Body for ``POST /meal-plan`` — assign a recipe to a day."""

    date: str  # ISO 'YYYY-MM-DD'
    recipe_uuid: str


class MealPlanEntryUpdate(BaseModel):
    """Body for ``PATCH /meal-plan/{id}`` — move/reorder an entry."""

    date: Optional[str] = None
    position: Optional[int] = None


class MealPlanEntry(BaseModel):
    """A recipe assigned to a day, returned with its recipe title."""

    id: int
    date: str
    recipe_uuid: str
    recipe_title: str
    position: int


class DateRange(BaseModel):
    """A start/end date window (inclusive), ISO 'YYYY-MM-DD'."""

    start: str
    end: str
