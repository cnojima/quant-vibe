#!/bin/bash
# Script to rebuild the streaming container on remote instance
# Run this on your remote server where docker-compose is running

set -e  # Exit on error

echo "========================================================================"
echo "REBUILDING QUANT-VIBE STREAMING CONTAINER"
echo "========================================================================"
echo ""

# Step 1: Stop the streaming container
echo "Step 1: Stopping streaming container..."
docker-compose stop streaming
echo "✓ Container stopped"
echo ""

# Step 2: Remove the old container
echo "Step 2: Removing old container..."
docker-compose rm -f streaming
echo "✓ Container removed"
echo ""

# Step 3: Remove the old image (force rebuild)
echo "Step 3: Removing old image..."
docker rmi quant-vibe-streaming 2>/dev/null || docker rmi quant-vibe_streaming 2>/dev/null || echo "Image already removed"
echo "✓ Image removed"
echo ""

# Step 4: Rebuild the image
echo "Step 4: Rebuilding streaming image..."
echo "This will take a few minutes..."
docker-compose build --no-cache streaming
echo "✓ Image rebuilt"
echo ""

# Step 5: Start the container
echo "Step 5: Starting streaming container..."
docker-compose up -d streaming
echo "✓ Container started"
echo ""

# Step 6: Wait for container to be ready
echo "Step 6: Waiting for container to initialize..."
sleep 5
echo ""

# Step 7: Verify sqlalchemy is installed
echo "Step 7: Verifying SQLAlchemy installation..."
if docker exec quant-vibe-streaming python -c "import sqlalchemy; print('SQLAlchemy version:', sqlalchemy.__version__)" 2>/dev/null; then
    echo "✓ SQLAlchemy is installed!"
else
    echo "✗ SQLAlchemy verification failed"
    echo ""
    echo "Checking container logs for errors..."
    docker-compose logs --tail=50 streaming
    exit 1
fi
echo ""

# Step 8: Show logs
echo "========================================================================"
echo "REBUILD COMPLETE"
echo "========================================================================"
echo ""
echo "Showing last 30 lines of logs (press Ctrl+C to exit)..."
echo ""
docker-compose logs --tail=30 -f streaming

