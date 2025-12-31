import { useEffect, useRef, useState, useCallback } from 'react';
import type { WebSocketMessage } from '../types/api';

interface UseWebSocketOptions {
  onMessage?: (data: any) => void;
  onError?: (error: Event) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export function useWebSocket<T = any>(
  url: string,
  options: UseWebSocketOptions = {}
) {
  const {
    onMessage,
    onError,
    onConnect,
    onDisconnect,
    reconnectInterval = 5000,
    maxReconnectAttempts = 5,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Event | null>(null);

  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectCountRef = useRef(0);
  const isUnmountingRef = useRef(false);
  const isMountedRef = useRef(false);

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected, skipping');
      return;
    }
    if (ws.current && ws.current.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocket] Connection in progress, skipping');
      return;
    }
    try {
      const token = localStorage.getItem('auth_token');

      // Build WebSocket URL
      // Use environment variable if set, otherwise construct from current location
      const wsBaseUrl = (import.meta as any).env?.VITE_WS_BASE_URL;

      let wsUrl: string;
      if (wsBaseUrl) {
        // Use explicit WebSocket base URL (e.g., ws://localhost:8000)
        wsUrl = `${wsBaseUrl}${url}${token ? `?token=${token}` : ''}`;
      } else {
        // Construct from current window location
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        wsUrl = `${protocol}//${host}${url}${token ? `?token=${token}` : ''}`;
      }

      console.log('[WebSocket] Connecting to:', wsUrl);

      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('[WebSocket] Connected successfully');
        setIsConnected(true);
        setError(null);
        reconnectCountRef.current = 0;
        onConnect?.();
      };

      ws.current.onclose = (event) => {
        console.log('[WebSocket] Disconnected', { code: event.code, reason: event.reason, wasClean: event.wasClean });
        setIsConnected(false);
        onDisconnect?.();

        // Don't reconnect if component is unmounting
        if (isUnmountingRef.current) {
          console.log('[WebSocket] Component unmounting, not reconnecting');
          return;
        }

        // Attempt reconnection
        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          console.log(`[WebSocket] Reconnecting in ${reconnectInterval}ms... (attempt ${reconnectCountRef.current}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else {
          console.error('[WebSocket] Max reconnection attempts reached');
        }
      };

      ws.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('[WebSocket] Received:', message);

          // Handle different message formats from backend
          // Backend sends: { type: 'connection'|'event'|'heartbeat', data/topic/message: ... }
          if (message.type === 'connection') {
            // Welcome message, ignore
            console.log('[WebSocket] Welcome:', message.message);
          } else if (message.type === 'pong') {
            // Pong response, ignore
          } else if (message.topic) {
            // Redis pub/sub message: { topic: 'trading.signal', data: {...} }
            setData(message);
            onMessage?.(message);
          } else {
            // Generic message
            setData(message.data || message);
            onMessage?.(message.data || message);
          }
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err, event.data);
        }
      };

      ws.current.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError(event);
        onError?.(event);
      };
    } catch (err) {
      console.error('[WebSocket] Failed to create connection:', err);
    }
  }, [url, onMessage, onError, onConnect, onDisconnect, reconnectInterval, maxReconnectAttempts])

  useEffect(() => {
    isUnmountingRef.current = false;
    connect();

    // Send periodic ping to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        console.log('[WebSocket] Sending ping');
        ws.current.send('ping');
      }
    }, 30000); // Every 30 seconds

    return () => {
      console.log('[WebSocket] Cleanup: clearing interval');
      clearInterval(pingInterval);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }

      // Only close WebSocket when component is truly unmounting
      // In React StrictMode (development), cleanup runs twice but we want to keep the connection
      // Set a small timeout to check if component is remounting (StrictMode) or truly unmounting
      const cleanupTimeout = setTimeout(() => {
        if (ws.current) {
          console.log('[WebSocket] Cleanup: closing connection (true unmount)');
          isUnmountingRef.current = true;
          ws.current.close();
          ws.current = null;
        }
      }, 100);

      // If component remounts quickly (StrictMode), this will be cleared
      return () => {
        clearTimeout(cleanupTimeout);
      };
    };
  }, [connect]);

  const send = useCallback((data: any) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (ws.current) {
      ws.current.close();
    }
  }, []);

  return {
    data,
    isConnected,
    error,
    send,
    disconnect,
    reconnect: connect,
  };
}
