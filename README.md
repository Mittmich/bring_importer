# Recipe to Bring Importer

This is a Progressive Web App (PWA) that lets you upload recipe photos, extract ingredients using OpenAI's Vision API, and import them directly to your Bring shopping list.

## Features

- **Photo Upload**: Take a photo of a recipe or upload an existing one
- **AI-Powered Recipe Parsing**: Uses OpenAI's Vision API to extract recipe information
- **Bring Integration**: Import ingredients directly to the Bring shopping list app
- **Works Offline**: Install as a PWA for offline access
- **Secure**: Your OpenAI API key is stored locally and never sent to any server other than OpenAI

## How to Use

1. Click the settings (⚙️) icon on the sidebar to add your OpenAI API key
2. Upload a photo of a recipe
3. Click "Parse Recipe" to extract the recipe information
4. Review the extracted ingredients
5. Click "Import to Bring" to add ingredients to your Bring shopping list

## Setup & Installation

### Backend (FastAPI)

The backend server uses FastAPI and requires Python 3.8 or later.

#### Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and virtual environment manager.

1. Install uv if you don't have it yet:
   ```bash
   pip install uv
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r requirements.txt
   # Or using pyproject.toml
   uv pip install -e .
   ```

3. Create a `.env` file with your OpenAI API key and a secret key:
   ```
   OPENAI_API_KEY=your_openai_api_key
   SECRET_KEY=a_random_secret_key_for_jwt_tokens
   ```

4. Start the server:
   ```bash
   python api.py
   ```
   The API will be available at http://localhost:8001

#### Using pip

If you prefer using pip:

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Follow steps 3-4 from the uv setup above.

### Frontend

After setting up the backend, you need to serve the frontend files.

```bash
# Using any local server, e.g. with Python:
python -m http.server 8000
```

Then navigate to http://localhost:8000 in your browser.

### Requirements

- Python 3.8 or higher for the backend
- An OpenAI API key with access to the GPT-4o model
- A modern web browser (Chrome, Firefox, Safari, Edge)

## Tech Stack

- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5
- **Backend**: FastAPI, SQLite, JWT authentication
- **APIs**: OpenAI GPT-4o for image processing, Bring API for shopping list integration
- **PWA Features**: Service Worker API for offline capabilities

## Privacy Notice

This app stores user credentials and parsed recipes in a SQLite database on the server. Your OpenAI API key is stored only on the server and used for processing images. User authentication is handled with secure JWT tokens.
