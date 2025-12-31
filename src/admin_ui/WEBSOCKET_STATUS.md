# WebSocket Status

## Current State: DISABLED

WebSocket real-time updates are **disabled** in the Live Trading Monitor. The application uses REST API polling instead.

## Why Disabled?

WebSocket connections have compatibility issues with the current development setup:

1. **React StrictMode**: React 18's StrictMode intentionally double-mounts components in development, causing WebSocket connections to be created and immediately destroyed
2. **Docker Networking**: Connections from external IP through Docker port forwarding add network complexity
3. **Race Conditions**: Frontend cleanup functions were closing connections before they could fully establish

## Current Solution

The Live Trading Monitor uses **REST API polling** via React Query:
- `useLiveStatus()` - polls `/api/live/status`
- `useLivePositions()` - polls `/api/live/positions`
- `useLiveOrders()` - polls `/api/live/orders`
- `useLiveEvents()` - polls `/api/live/events`
- `useLiveStats()` - polls `/api/live/stats`

Polling provides adequate real-time updates (every few seconds) without the complexity of WebSocket management.

## How to Re-Enable WebSocket

### Option 1: Production Build (Recommended)

WebSocket should work fine in production builds where React StrictMode is disabled:

1. Build the frontend for production:
   ```bash
   cd src/admin_ui/frontend
   npm run build
   ```

2. In `LiveTradingMonitor.tsx`, uncomment the WebSocket code:
   ```typescript
   const { isConnected } = useWebSocket('/ws/events', {
     onMessage: (data) => {
       const topic = data?.topic || '';
       if (!topic.includes('heartbeat')) {
         console.log('[LiveMonitor] WS Event:', topic, data);
       }
     },
     onConnect: () => console.log('[LiveMonitor] WebSocket connected'),
     onDisconnect: () => console.log('[LiveMonitor] WebSocket disconnected'),
     reconnectInterval: 5000,
     maxReconnectAttempts: 10,
   });
   ```

3. Remove the line: `const isConnected = false;`

### Option 2: Disable StrictMode (Not Recommended)

In `src/admin_ui/frontend/src/main.tsx`, remove `<React.StrictMode>`:

```typescript
ReactDOM.createRoot(document.getElementById('root')!).render(
  <App />  // Remove <React.StrictMode> wrapper
);
```

**Warning**: This disables important development checks and is not recommended.

### Option 3: Test Without Docker

Run the backend directly (not in Docker) to avoid networking issues:

```bash
cd src/admin_ui/backend
uvicorn admin_ui.backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Backend WebSocket Implementation

The backend WebSocket endpoint is **fully implemented and working** at:
- **Endpoint**: `/ws/events`
- **Authentication**: Optional JWT token via query parameter `?token=...`
- **Protocol**: JSON messages with format `{ type: 'connection'|'event'|'pong', ...data }`
- **Features**:
  - Redis pub/sub integration (subscribed to `trading.*`, `system.*`, `heartbeat.*`)
  - Automatic message broadcasting to all connected clients
  - Ping/pong keep-alive support
  - Graceful disconnect handling

## Implementation Details

### Frontend Hook: `src/admin_ui/frontend/src/hooks/useWebSocket.ts`

Features:
- ✅ Automatic reconnection with exponential backoff
- ✅ StrictMode-aware cleanup (100ms timeout to detect true unmount)
- ✅ Duplicate connection prevention
- ✅ Periodic ping every 30 seconds
- ✅ Comprehensive logging
- ✅ Message format handling for different backend message types

### Backend Endpoint: `src/admin_ui/backend/main.py`

```python
@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    register_websocket(websocket)

    # Send welcome message
    await websocket.send_json({
        "type": "connection",
        "message": "Connected to live trading events"
    })

    # Keep connection alive and handle messages
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            break
        elif message["type"] == "websocket.receive":
            if message.get("text") == "ping":
                await websocket.send_json({"type": "pong"})
```

### Redis Integration: `src/admin_ui/backend/redis_client.py`

The backend subscribes to Redis topics and broadcasts to WebSocket clients:
- `trading.*` - trading signals, orders, fills
- `system.*` - system events, errors
- `heartbeat.*` - service heartbeats

## Testing WebSocket

To test if WebSocket is working:

1. Open browser console
2. Connect manually:
   ```javascript
   const ws = new WebSocket('ws://localhost:8000/ws/events');
   ws.onopen = () => console.log('Connected');
   ws.onmessage = (e) => console.log('Message:', e.data);
   ws.onerror = (e) => console.error('Error:', e);
   ws.onclose = (e) => console.log('Closed:', e.code, e.reason);
   ```

3. Check for welcome message:
   ```json
   {"type": "connection", "message": "Connected to live trading events", "timestamp": 1234567890}
   ```

4. Test ping/pong:
   ```javascript
   ws.send('ping');
   // Should receive: {"type": "pong"}
   ```

5. Publish test event to Redis:
   ```bash
   docker exec quant-vibe-admin-ui python -c "
   import asyncio
   import json
   import redis.asyncio as aioredis

   async def test():
       r = await aioredis.from_url('redis://192.168.100.197:6379/0', encoding='utf-8', decode_responses=True)
       await r.publish('trading.test', json.dumps({'test': 'message'}))
       await r.aclose()

   asyncio.run(test())
   "
   ```

## Future Improvements

1. **Production deployment**: Deploy with production React build (no StrictMode)
2. **Connection pooling**: Implement WebSocket connection pooling for better performance
3. **Message filtering**: Allow clients to subscribe to specific topics
4. **Compression**: Add WebSocket compression for large message payloads
5. **Heartbeat monitoring**: Detect and remove dead connections
6. **Rate limiting**: Prevent abuse by limiting message rates

## Related Files

- Frontend hook: `src/admin_ui/frontend/src/hooks/useWebSocket.ts`
- Frontend component: `src/admin_ui/frontend/src/pages/LiveTradingMonitor.tsx`
- Backend endpoint: `src/admin_ui/backend/main.py` (line 124-167)
- Backend Redis client: `src/admin_ui/backend/redis_client.py`
- Backend types: `src/admin_ui/frontend/src/types/api.ts` (WebSocketMessage)

## References

- [React StrictMode double-mounting issue](https://github.com/facebook/react/issues/24502)
- [FastAPI WebSocket documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [WebSocket API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
