from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, status, Form, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
import sqlite3
import uuid
import base64
import os
import json
import requests
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "please_change_this_to_a_random_key_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000

app = FastAPI(title="Recipe Parser API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
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

class Recipe(BaseModel):
    title: str
    recipeIngredient: List[str]
    recipeYield: str = "4 servings"
    datePublished: Optional[str] = None
    description: Optional[str] = None
    html_content: Optional[str] = None

# Database setup
def get_db_connection():
    conn = sqlite3.connect('recipes.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    )
    ''')
    
    # Create recipes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes (
        uuid TEXT PRIMARY KEY,
        user_id INTEGER,
        title TEXT,
        recipe_json TEXT,  -- This can store large text including HTML content
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database and users on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# Authentication functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return UserInDB(email=user['email'], password="", hashed_password=user['hashed_password'])
    return None

def authenticate_user(email: str, password: str):
    user = get_user(email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user(email=token_data.email)
    if user is None:
        raise credentials_exception
    return user

def get_user_id(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result['id']
    return None

# Parse recipe with OpenAI
def parse_recipe_with_openai(image_base64: str) -> Recipe:
    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}'
    }
    
    # Ensure base64 is properly formatted
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,")[1]
    
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that extracts recipe information from images. The most important ascept of the recipe is the ingredients, which must be included in the recipeIngredient itemprop. Return a valid HTML with proper schema.org/Recipe markup."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Extract the recipe information from this image. Return a valid HTML with proper schema.org/Recipe markup. Include itemscope, itemtype, and itemprop attributes to make it fully compliant with schema.org/Recipe. It is vital that all ingredients individually receive the recipeIngredient itemprop. Do not include JSON blocks in your response, only return valid HTML."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {response.text}")
    
    result = response.json()
    html_content = result['choices'][0]['message']['content']
    
    # Extract HTML recipe content
    try:
        # Extract recipe data from HTML using basic parsing
        from bs4 import BeautifulSoup
        import re
        
        # Clean up the HTML content - remove markdown code blocks if present
        if "```html" in html_content:
            html_match = re.search(r"```html\s*(.*?)\s*```", html_content, re.DOTALL)
            if html_match:
                html_content = html_match.group(1)
        elif "```" in html_content:
            html_match = re.search(r"```\s*(.*?)\s*```", html_content, re.DOTALL)
            if html_match:
                html_content = html_match.group(1)
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find recipe element
        recipe_element = soup.find(itemtype=re.compile(r'schema.org/Recipe'))
        
        if not recipe_element:
            # Try alternate format
            recipe_element = soup.find(attrs={"itemtype": re.compile(r'schema.org/Recipe')})
            
        if not recipe_element:
            # If still not found, use the entire soup
            recipe_element = soup
        
        # Extract title
        title_element = recipe_element.find(attrs={"itemprop": "name"})
        title = title_element.text.strip() if title_element else "Untitled Recipe"
        
        # Extract ingredients
        ingredient_elements = recipe_element.find_all(attrs={"itemprop": "recipeIngredient"})
        ingredients = [ing.text.strip() for ing in ingredient_elements]
        
        # If no specific ingredients found, look for list items
        if not ingredients and recipe_element.find('ul'):
            ingredients = [li.text.strip() for li in recipe_element.find('ul').find_all('li')]
        
        # Extract yield
        yield_element = recipe_element.find(attrs={"itemprop": "recipeYield"})
        recipe_yield = yield_element.text.strip() if yield_element else "4 servings"
        
        # Extract description
        description_element = recipe_element.find(attrs={"itemprop": "description"})
        description = description_element.text.strip() if description_element else ""
        
        # Create recipe object
        recipe = Recipe(
            title=title,
            recipeIngredient=ingredients,
            recipeYield=recipe_yield,
            description=description,
            datePublished=datetime.now().strftime("%Y-%m-%d"),
            html_content=str(soup)
        )
        return recipe
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse recipe: {str(e)}")

# API Endpoints

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/recipes/parse", response_model=RecipeResponse)
async def parse_recipe(
    image: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    try:
        # Parse recipe using OpenAI
        recipe = parse_recipe_with_openai(image)
        
        # Generate UUID
        recipe_uuid = str(uuid.uuid4())
        
        # Get user ID
        user_id = get_user_id(current_user.email)
        
        # Create full recipe JSON (schema.org format)
        schema_recipe = {
            "@context": "https://schema.org/",
            "@type": "Recipe",
            "name": recipe.title,
            "recipeIngredient": recipe.recipeIngredient,
            "recipeYield": recipe.recipeYield,
            "datePublished": recipe.datePublished,
            "description": recipe.description,
            "html_content": recipe.html_content  # Add HTML content to the stored data
        }
        
        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recipes (uuid, user_id, title, recipe_json) VALUES (?, ?, ?, ?)",
            (recipe_uuid, user_id, recipe.title, json.dumps(schema_recipe))
        )
        conn.commit()
        conn.close()
        
        # Generate URL for recipe
        recipe_url = f"/recipes/{recipe_uuid}.json"
        
        return RecipeResponse(uuid=recipe_uuid, url=recipe_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing recipe: {str(e)}")

@app.get("/recipes/{recipe_uuid}.json")
async def get_recipe(recipe_uuid: str):
    # This endpoint doesn't require authentication
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,))
    recipe = cursor.fetchone()
    conn.close()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return JSONResponse(content=json.loads(recipe['recipe_json']))

@app.get("/recipes/{recipe_uuid}.html")
async def get_recipe_html(recipe_uuid: str):
    # This endpoint returns the HTML content directly
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT recipe_json FROM recipes WHERE uuid = ?", (recipe_uuid,))
    recipe = cursor.fetchone()
    conn.close()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    recipe_data = json.loads(recipe['recipe_json'])
    html_content = recipe_data.get('html_content')
    
    if not html_content:
        raise HTTPException(status_code=404, detail="No HTML content available for this recipe")
    
    # Return the HTML content with the appropriate content type
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/recipes", response_model=List[Dict[str, Any]])
async def list_recipes():
    """Return a list of all recipes (uuid, title, datePublished if available)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, title, recipe_json FROM recipes ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    recipes = []
    for row in rows:
        try:
            recipe_json = json.loads(row['recipe_json'])
            date_published = recipe_json.get('datePublished', None)
        except Exception:
            date_published = None
        recipes.append({
            'uuid': row['uuid'],
            'title': row['title'],
            'datePublished': date_published
        })
    return recipes

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
