// frontend/src/contexts/WebSocketContext.tsx
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { tokenStorage } from "@/utils/api";
import type { WSMessage, WSEventType } from "@/types";

type Listener = (data: unknown) => void;

interface WSContextValue {
  isConnected: boolean;
  subscribe:   (event: WSEventType, fn: Listener) => () => void;
  send:        (msg: object) => void;
}

const WS_URL = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") + "/ws";
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT = 10;

const WebSocketContext = createContext<WSContextValue | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const wsRef        = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Map<WSEventType, Set<Listener>>>(new Map());
  const retryRef     = useRef(0);
  const timerRef     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    const token = tokenStorage.getAccess();
    if (!token) return;
    const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
    const ws  = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen    = () => { setIsConnected(true); retryRef.current = 0; };
    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data);
        listenersRef.current.get(msg.event)?.forEach(fn => fn(msg.data));
      } catch { /* ignore */ }
    };
    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (retryRef.current < MAX_RECONNECT) {
        retryRef.current++;
        timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };
    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => { if (timerRef.current) clearTimeout(timerRef.current); wsRef.current?.close(); };
  }, [connect]);

  const subscribe = useCallback((event: WSEventType, fn: Listener) => {
    if (!listenersRef.current.has(event)) listenersRef.current.set(event, new Set());
    listenersRef.current.get(event)!.add(fn);
    return () => listenersRef.current.get(event)?.delete(fn);
  }, []);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(msg));
  }, []);

  return (
    <WebSocketContext.Provider value={{ isConnected, subscribe, send }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WSContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket باید داخل WebSocketProvider استفاده شود");
  return ctx;
}
