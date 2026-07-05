import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

type WSEventType = "positions" | "signals" | "metrics" | "alert" | "ping";
type Listener    = (data: unknown) => void;

interface WSContextValue {
  isConnected: boolean;
  subscribe:   (event: WSEventType, fn: Listener) => () => void;
  send:        (msg: object) => void;
}

const WebSocketContext = createContext<WSContextValue | null>(null);

// BUG-P6 FIX: exponential backoff constants
const WS_BACKOFF_BASE_MS = 1_000;   // 1 s first retry
const WS_BACKOFF_MAX_MS  = 30_000;  // 30 s cap
const WS_MAX_RETRIES     = 10;

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef       = useRef<WebSocket | null>(null);
  const listenersRef= useRef<Map<WSEventType, Set<Listener>>>(new Map());
  const mountedRef  = useRef(false);
  const timerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  // BUG-P6: track retry count for backoff
  const retryRef    = useRef(0);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const wsUrl =
      (import.meta as { env?: { VITE_WS_URL?: string } }).env?.VITE_WS_URL ??
      `${window.location.protocol === "https:" ? "wss" : "ws"}://${
        window.location.host
      }/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setIsConnected(true);
      retryRef.current = 0;   // BUG-P6: reset on successful connect
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as { type?: WSEventType; data?: unknown };
        const listeners = listenersRef.current.get(msg.type as WSEventType);
        listeners?.forEach((fn) => fn(msg.data));
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);

      const attempt = retryRef.current;
      if (attempt >= WS_MAX_RETRIES) {
        // BUG-P6: give up after max retries — avoids connection storm
        console.warn("[WS] max reconnect attempts reached — giving up");
        return;
      }

      // BUG-P6: exponential backoff with jitter
      const backoff = Math.min(
        WS_BACKOFF_BASE_MS * Math.pow(2, attempt) + Math.random() * 500,
        WS_BACKOFF_MAX_MS
      );
      retryRef.current = attempt + 1;

      timerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, backoff);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback((event: WSEventType, fn: Listener) => {
    if (!listenersRef.current.has(event)) listenersRef.current.set(event, new Set());
    listenersRef.current.get(event)!.add(fn);
    return () => listenersRef.current.get(event)?.delete(fn);
  }, []);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify(msg));
  }, []);

  return (
    <WebSocketContext.Provider value={{ isConnected, subscribe, send }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WSContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket خارج از WebSocketProvider استفاده شده");
  return ctx;
}
