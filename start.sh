#!/bin/zsh

# Script to start the Recipe to Bring application
# This starts the FastAPI backend and Nginx for serving the frontend

# Configuration
BACKEND_DIR="$(pwd)/backend"
NGINX_CONF="$(pwd)/nginx.conf"
NGINX_PORT=80
BACKEND_PORT=8001
LOG_DIR="$(pwd)/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if running as root (needed for port 80)
if [ "$NGINX_PORT" -lt 1024 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Warning: Nginx is configured to use port $NGINX_PORT, which requires root privileges."
  echo "Either run this script with sudo or change the port in nginx.conf."
  exit 1
fi

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check required dependencies
echo "Checking dependencies..."
if ! command_exists nginx; then
  echo "Error: nginx is not installed. Please install it first."
  echo "To install on macOS: brew install nginx"
  exit 1
fi

if ! command_exists python3; then
  echo "Error: python3 is not installed."
  exit 1
fi

echo "Starting Recipe to Bring application..."

# Start the FastAPI backend
echo "Starting backend server on port $BACKEND_PORT..."
cd "$BACKEND_DIR" || { echo "Error: Could not change to backend directory"; exit 1; }

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
  source .venv/bin/activate
  echo "Activated Python virtual environment"
fi

# Start the backend in the background
python3 run.py > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Check if backend started successfully
sleep 2
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  echo "Error: Backend failed to start. Check logs at $LOG_DIR/backend.log"
  exit 1
fi

# Write PID to file
echo $BACKEND_PID > "$LOG_DIR/backend.pid"

# Start Nginx with our configuration
echo "Starting Nginx on port $NGINX_PORT..."
nginx -c "$NGINX_CONF" > "$LOG_DIR/nginx.log" 2>&1

if [ $? -ne 0 ]; then
  echo "Error: Failed to start Nginx. Check logs at $LOG_DIR/nginx.log"
  # Kill backend if Nginx fails
  kill $BACKEND_PID
  exit 1
fi

echo "Application started successfully!"
echo "Frontend available at http://localhost:$NGINX_PORT"
echo
echo "To stop the application, run ./stop.sh"
