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
ACCESS_TOKEN_EXPIRE_MINUTES = 30
USERS_FILE = os.getenv("USERS_FILE", "users.json")

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
        recipe_json TEXT,
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
    init_users_from_file()

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
                "content": "You are a helpful assistant that extracts recipe information from images."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the recipe information from this image. Return a JSON with these fields: title (string), recipeIngredient (array of strings, each representing one ingredient with quantity), recipeYield (string), description (optional string). Format following the schema.org Recipe format."
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
        "max_tokens": 1500
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {response.text}")
    
    result = response.json()
    content = result['choices'][0]['message']['content']
    
    # Extract JSON from the response
    try:
        # Try to find JSON block in markdown format
        json_match = None
        if "```json" in content and "```" in content.split("```json")[1]:
            json_match = content.split("```json")[1].split("```")[0].strip()
        
        # If not found, try to extract the entire content as JSON
        if not json_match:
            json_match = content
            
        recipe_data = json.loads(json_match)
        
        # Ensure proper schema.org format
        recipe = Recipe(
            title=recipe_data.get("title", "Untitled Recipe"),
            recipeIngredient=recipe_data.get("recipeIngredient", recipe_data.get("items", [])),
            recipeYield=recipe_data.get("recipeYield", "4 servings"),
            description=recipe_data.get("description", ""),
            datePublished=datetime.now().strftime("%Y-%m-%d")
        )
        return recipe
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse recipe: {str(e)}")

def init_users_from_file():
    """Initialize users from a JSON file."""
    try:
        # Check if users table is empty
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if user_count > 0:
            print(f"Database already contains {user_count} users. Skipping initialization.")
            conn.close()
            return
            
        # Load users from JSON file
        if not os.path.exists(USERS_FILE):
            print(f"Warning: Users file {USERS_FILE} not found. No users imported.")
            conn.close()
            return
            
        with open(USERS_FILE, 'r') as f:
            users_data = json.load(f)
            
        if 'users' not in users_data or not isinstance(users_data['users'], list):
            print("Warning: Invalid users.json format. Expected 'users' array.")
            conn.close()
            return
            
        # Insert users into database
        for user in users_data['users']:
            if 'email' in user and 'hashed_password' in user:
                cursor.execute(
                    "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
                    (user['email'], user['hashed_password'])
                )
                print(f"Added user: {user['email']}")
                
        conn.commit()
        conn.close()
        print(f"Users initialization complete. Imported {len(users_data['users'])} users.")
    except Exception as e:
        print(f"Error initializing users: {e}")

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
            "description": recipe.description
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

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
