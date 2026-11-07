"""Pydantic request/response models shared by the routers."""

from datetime import date as _date
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    id: int = 0
    is_admin: bool = False
    disabled: bool = False
    # Must match the JWT's ``ver`` claim; bumping it revokes all sessions.
    token_version: int = 0


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
    # Language code of the text content (see api/i18n.py); None = unknown.
    inLanguage: Optional[str] = None


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
    # Which language variant the content fields belong to. A code with a stored
    # translation edits that translation; anything else edits the base content.
    language: Optional[str] = None
    # Declare the language of the base content (e.g. for legacy recipes).
    inLanguage: Optional[str] = None
    # Optimistic concurrency: the ``updated_at`` the client loaded. If it no
    # longer matches the stored value, someone else edited first → 409.
    base_updated_at: Optional[str] = None


class ManualRecipe(BaseModel):
    """Body for ``POST /recipes`` — a recipe entered by hand."""

    title: str
    ingredients: List[Ingredient] = []
    instructions: List[InstructionStep] = []
    recipeYield: str = ""
    description: Optional[str] = None
    note: Optional[str] = None
    # Language the content is written in (default: request/profile language).
    language: Optional[str] = None
    # Ingredients typed one per line ("500 g flour"); appended after ``ingredients``.
    ingredients_text: Optional[str] = None
    tags: List[str] = []
    is_public: bool = False


class TranslateRequest(BaseModel):
    """Body for ``POST /recipes/{uuid}/translate``."""

    language: str


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


# ---------------------------------------------------------------------------
# Menus with prep planning (api/routers/menus.py). Times are minutes after
# midnight; durations and leads are minutes.
# ---------------------------------------------------------------------------

Equipment = Literal["", "oven", "stove", "fridge"]


def _iso_date_or_none(v: Optional[str]) -> Optional[str]:
    if v in (None, ""):
        return None
    _date.fromisoformat(v)  # raises ValueError -> 422
    return v


class MenuCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    date: Optional[str] = None  # ISO 'YYYY-MM-DD'
    guests: int = Field(default=4, ge=1, le=50)

    _check_date = field_validator("date")(_iso_date_or_none)


class MenuUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    date: Optional[str] = None  # "" clears it
    guests: Optional[int] = Field(default=None, ge=1, le=50)

    @field_validator("date")
    @classmethod
    def _date_ok(cls, v: Optional[str]) -> Optional[str]:
        if v == "":
            return v
        return _iso_date_or_none(v)


class MenuCourseCreate(BaseModel):
    recipe_uuid: str
    name: Optional[str] = Field(default=None, max_length=60)
    serve: Optional[int] = Field(default=None, ge=0, le=1439)


class MenuCourseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    serve: Optional[int] = Field(default=None, ge=0, le=1439)
    position: Optional[int] = Field(default=None, ge=0)


class MenuStepCreate(BaseModel):
    course_id: int
    name: str = Field(min_length=1, max_length=120)
    duration: int = Field(default=15, ge=1, le=1440)
    day: Literal[0, -1] = 0
    lead: int = Field(default=0, ge=0, le=1440)
    at: Optional[int] = Field(default=None, ge=0, le=1439)
    hands: bool = True
    equipment: Equipment = ""
    temp: Optional[int] = Field(default=None, ge=50, le=300)


class MenuStepUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    duration: Optional[int] = Field(default=None, ge=1, le=1440)
    day: Optional[Literal[0, -1]] = None
    lead: Optional[int] = Field(default=None, ge=0, le=1440)
    at: Optional[int] = Field(default=None, ge=0, le=1439)
    hands: Optional[bool] = None
    equipment: Optional[Equipment] = None
    temp: Optional[int] = Field(default=None, ge=50, le=300)
    done: Optional[bool] = None
