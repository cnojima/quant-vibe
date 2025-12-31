#!/bin/bash
# Start Admin UI in development mode (both backend and frontend)
#
# Usage:
#   ./scripts/start_admin_ui_dev.sh
#
# This script starts both the FastAPI backend and React frontend in development mode.
# Both processes run with hot reload enabled.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting Quant-Vibe Admin UI (Development Mode)"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if backend dependencies are installed
echo -e "${BLUE}Checking Python dependencies...${NC}"
if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Backend dependencies not found. Installing...${NC}"
    pip install -e ".[admin_ui]"
fi

# Check if frontend dependencies are installed
echo -e "${BLUE}Checking Node.js dependencies...${NC}"
if [ ! -d "$PROJECT_ROOT/src/admin_ui/frontend/node_modules" ]; then
    echo -e "${YELLOW}⚠️  Frontend dependencies not found. Installing...${NC}"
    cd "$PROJECT_ROOT/src/admin_ui/frontend"
    npm install
    cd "$PROJECT_ROOT"
fi

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Please create one with required variables.${NC}"
    echo "Required variables: ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET_KEY"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Dependencies ready${NC}"
echo ""
echo "Starting services..."
echo ""
echo "  Backend:  http://localhost:8000 (FastAPI + Uvicorn)"
echo "  Frontend: http://localhost:5173 (React + Vite)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop both services${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend in background
echo -e "${BLUE}[Backend]${NC} Starting FastAPI server..."
cd "$PROJECT_ROOT"
python scripts/run_admin_ui.py --reload &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 2

# Start frontend in background
echo -e "${BLUE}[Frontend]${NC} Starting Vite dev server..."
cd "$PROJECT_ROOT/src/admin_ui/frontend"
npm run dev &
FRONTEND_PID=$!

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
