import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessage, WSMessageType } from "../types";

type Handler<T = unknown> = (data: T) => void;

interface UseWebSocketOptions {
  url?: string;
  reconnectDelay?: number;
  maxRetries?: number;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    url = `ws://${window.location.hostname}:8000/ws`,
    reconnectDelay = 3000,
    maxRetries = 10,
  } = options;

  const ws = useRef<WebSocket | null>(null);
  const handlers = useRef<Map<WSMessageType, Handler[]>>(new Map());
  const retries = useRef(0);
  const [connected, setConnected] = useState(false);
  const [lastPing, setLastPing] = useState<Date | null>(null);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    try {
      const token = localStorage.getItem("gv_token");
      const fullUrl = token ? `${url}?token=${token}` : url;
      ws.current = new WebSocket(fullUrl);

      ws.current.onopen = () => {
        setConnected(true);
        retries.current = 0;
        setLastPing(new Date());
      };

      ws.current.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          setLastPing(new Date());
          const list = handlers.current.get(msg.type as WSMessageType) ?? [];
          list.forEach((fn) => fn(msg.data));
          const allHandlers = handlers.current.get("*" as WSMessageType) ?? [];
          allHandlers.forEach((fn) => fn(msg));
        } catch {
          // ignore parse errors
        }
      };

      ws.current.onclose = () => {
        setConnected(false);
        if (retries.current < maxRetries) {
          retries.current += 1;
          setTimeout(connect, reconnectDelay);
        }
      };

      ws.current.onerror = () => {
        ws.current?.close();
      };
    } catch {
      setConnected(false);
    }
  }, [url, reconnectDelay, maxRetries]);

  useEffect(() => {
    connect();
    return () => {
      ws.current?.close();
    };
  }, [connect]);

  const on = useCallback(<T>(type: WSMessageType | "*", handler: Handler<T>) => {
    const key = type as WSMessageType;
    const existing = handlers.current.get(key) ?? [];
    handlers.current.set(key, [...existing, handler as Handler]);
    return () => {
      const updated = (handlers.current.get(key) ?? []).filter((h) => h !== handler);
      handlers.current.set(key, updated);
    };
  }, []);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  }, []);

  return { connected, lastPing, on, send };
}
