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

### Requirements

- An OpenAI API key with access to the GPT-4 Vision API
- A modern web browser (Chrome, Firefox, Safari, Edge)

### Local Development

```bash
# Using any local server, e.g. with Python:
python -m http.server 8000
```

Or use any other static file server to serve the app locally.

## Tech Stack

- HTML5, CSS3, JavaScript
- Bootstrap 5 for UI components
- OpenAI Vision API for image processing
- Bring API for shopping list integration
- Service Worker API for offline capabilities

## Privacy Notice

This app does not collect or store any data on any server. Your OpenAI API key is stored locally in your browser's localStorage and is only sent to OpenAI when processing images.
