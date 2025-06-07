#!/bin/bash

# Script to stop the Recipe to Bring application
# This stops the FastAPI backend and Nginx

# Configuration
LOG_DIR="$(pwd)/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"

echo "Stopping Recipe to Bring application..."

# Stop Nginx
echo "Stopping Nginx..."
nginx -s stop
if [ $? -eq 0 ]; then
  echo "Nginx stopped successfully"
else
  echo "Warning: Failed to stop Nginx properly. It might not be running."
fi

# Stop the backend
if [ -f "$BACKEND_PID_FILE" ]; then
  BACKEND_PID=$(cat "$BACKEND_PID_FILE")
  
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Stopping backend server (PID: $BACKEND_PID)..."
    kill "$BACKEND_PID"
    
    # Wait for backend to stop
    for i in $(seq 1 5); do
      if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        break
      fi
      echo "Waiting for backend to stop..."
      sleep 1
    done
    
    # Force kill if still running
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "Backend not responding, forcing termination..."
      kill -9 "$BACKEND_PID"
    fi
    
    echo "Backend stopped"
  else
    echo "Backend is not running"
  fi
  
  rm "$BACKEND_PID_FILE"
else
  echo "Backend PID file not found. The server might not be running."
fi

echo "Application stopped successfully!"
