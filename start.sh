#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activate virtual environment
VENV_DIR="$PROJECT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Virtual environment activated: $VENV_DIR"
else
    echo "WARNING: No venv found at $VENV_DIR"
fi
echo ""
echo "=== AI Todo Board ==="
echo ""

# Kill existing processes on our ports
echo "[1/2] Cleaning up old processes..."
lsof -ti:9526 | xargs kill -9 2>/dev/null || true
sleep 1

# Start FastAPI server
echo "[2/2] Starting server on port 9526..."
cd "$PROJECT_DIR"
python main.py &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

echo ""
echo "Service started!"
echo "  Dashboard: http://localhost:9526"
echo ""
echo "Press Ctrl+C to stop."
cleanup() {
    echo ""
    echo "Stopping service..."
    kill $SERVER_PID 2>/dev/null || true
    echo "Done."
    exit 0
}
trap cleanup SIGINT SIGTERM
wait
