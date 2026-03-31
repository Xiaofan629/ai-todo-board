#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
VENV_DIR="$PROJECT_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Virtual environment activated: $VENV_DIR"
else
    echo "WARNING: No .venv found at $VENV_DIR"
fi
echo ""
echo "=== WeCom Bot + Agent Todo Dashboard ==="
echo ""

# Kill existing processes on our ports
echo "[1/3] Cleaning up old processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:8001 | xargs kill -9 2>/dev/null || true
sleep 1

# Start agent.py API server on port 8001
echo "[2/3] Starting Agent API server on port 8001..."
cd "$PROJECT_DIR"
AGENT_API_MODE=true AGENT_API_PORT=8001 python agent.py &
AGENT_PID=$!
echo "Agent PID: $AGENT_PID"

# Wait for agent to be ready
sleep 3
# Start wecom-bot FastAPI server on port 8000
echo "[3/3] Starting WeCom Bot server on port 8000..."
cd "$SCRIPT_DIR"
python main.py &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

echo ""
echo "All services started!"
echo "  Agent API:  http://localhost:8001"
echo "  Dashboard: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all services."
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $AGENT_PID 2>/dev/null || true
    kill $SERVER_PID 2>/dev/null || true
    echo "Done."
    exit 0
}
trap cleanup SIGINT SIGTERM
wait
