// frontend/src/contexts/WebSocketContext.tsx
// J-FIX-2: Exponential backoff reconnect (was fixed 3000ms — caused server flood on outage)
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { tokenStorage } from "@/utils/api";
import type { WSMessage, WSEventType } from "@/types";

type Listener = (data: unknown) => void;

interface WSContextValue {
  isConnected: boolean;
  subscribe:   (event: WSEventType, fn: Listener) => () => void;
  send:        (msg: object) => void;
}

const WS_URL      = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") + "/ws";
const MAX_RECONNECT       = 10;
const BASE_DELAY_MS       = 1_000;   // 1s initial
const MAX_DELAY_MS        = 30_000;  // 30s cap
const JITTER_FACTOR       = 0.3;     // ½30% jitter to avoid thundering-herd

/** Compute exponential-backoff delay with full jitter.
 *  attempt=0 → ~1s, attempt=3 → ~8s, attempt=6+ → ~30s (capped)
 */
function backoffDelay(attempt: number): number {
  const exp   = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = exp * JITTER_FACTOR * (Math.random() * 2 - 1); // [-30%, +30%]
  return Math.max(BASE_DELAY_MS, Math.round(exp + jitter));
}

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

    ws.onopen = () => {
      setIsConnected(true);
      retryRef.current = 0; // reset backoff on success
    };

    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data);
        listenersRef.current.get(msg.event)?.forEach(fn => fn(msg.data));
      } catch { /* ignore malformed frames */ }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      if (retryRef.current < MAX_RECONNECT) {
        const delay = backoffDelay(retryRef.current);
        retryRef.current++;
        // eslint-disable-next-line no-console
        console.debug(`[WS] reconnect attempt ${retryRef.current}/${MAX_RECONNECT} in ${delay}ms`);
        timerRef.current = setTimeout(connect, delay);
      } else {
        // eslint-disable-next-line no-console
        console.warn("[WS] max reconnect attempts reached — giving up");
      }
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback((event: WSEventType, fn: Listener) => {
    if (!listenersRef.current.has(event)) listenersRef.current.set(event, new Set());
    listenersRef.current.get(event)!.add(fn );
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
