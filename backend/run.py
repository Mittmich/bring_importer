#!/usr/bin/env python3

"""
Backend starter script for Recipe Parser API with URL prefix support.
This script starts the backend API with the /api prefix
to work with the Nginx reverse proxy configuration.
"""

import uvicorn
from api import app
from fastapi.middleware.wsgi import WSGIMiddleware

if __name__ == "__main__":
    # Run the app with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
