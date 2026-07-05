// frontend/src/contexts/WebSocketContext.tsx
// FIX-E7: WS_URL از WS_BASE_URL (config.ts) — نه VITE_WS_URL مستقیم
// FIX-E8: token از tokenStorage — نه localStorage مستقیم
// FIX-E9: mounted guard برای setState بعد از unmount
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { tokenStorage } from "@/utils/api";
import { WS_BASE_URL, WS_MAX_RECONNECT } from "@/utils/config";
import type { WSMessage, WSEventType } from "@/types";

type Listener = (data: unknown) => void;

interface WSContextValue {
  isConnected: boolean;
  subscribe:   (event: WSEventType, fn: Listener) => () => void;
  send:        (msg: object) => void;
}

const WS_URL        = `${WS_BASE_URL}/ws`;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS  = 30_000;
const JITTER        = 0.3;

function backoffDelay(attempt: number): number {
  const exp    = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = exp * JITTER * (Math.random() * 2 - 1);
  return Math.max(BASE_DELAY_MS, Math.round(exp + jitter));
}

const WebSocketContext = createContext<WSContextValue | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const wsRef        = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Map<WSEventType, Set<Listener>>>(new Map());
  const retryRef     = useRef(0);
  const timerRef     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef   = useRef(true);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const token = tokenStorage.getAccess();
    if (!token) return;

    const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
    const ws  = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setIsConnected(true);
      retryRef.current = 0;
    };

    ws.onmessage = (e) => {
      if (!mountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(e.data);
        listenersRef.current.get(msg.event)?.forEach(fn => fn(msg.data));
      } catch { /* ignore malformed frames */ }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);
      wsRef.current = null;
      if (retryRef.current < WS_MAX_RECONNECT) {
        const delay = backoffDelay(retryRef.current);
        retryRef.current++;
        timerRef.current = setTimeout(connect, delay);
      } else {
        // eslint-disable-next-line no-console
        console.warn("[WS] max reconnect attempts reached — giving up");
      }
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
  if (!ctx) throw new Error("useWebSocket باید داخل WebSocketProvider استفاده شود");
  return ctx;
}
