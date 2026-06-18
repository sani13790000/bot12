import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessageType } from "../types";
import { WS_URL } from "../utils/config";

type Handler = (data: unknown) => void;

export interface WSState {
  connected: boolean;
  reconnecting: boolean;
  latency: number;
}

export function useWebSocket() {
  const ws        = useRef<WebSocket | null>(null);
  const handlers  = useRef<Map<string, Set<Handler>>>(new Map());
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const pingTs    = useRef<number>(0);
  const retry     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount= useRef(0);
  const [state, setState] = useState<WSState>({ connected: false, reconnecting: false, latency: 0 });

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;
    setState(s => ({ ...s, reconnecting: retryCount.current > 0 }));
    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      retryCount.current = 0;
      setState({ connected: true, reconnecting: false, latency: 0 });
      pingTimer.current = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          pingTs.current = Date.now();
          socket.send(JSON.stringify({ type: "PING" }));
        }
      }, 15_000);
    };

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "PONG") {
          setState(s => ({ ...s, latency: Date.now() - pingTs.current }));
          return;
        }
        const set = handlers.current.get(msg.type);
        set?.forEach(fn => fn(msg.data));
        // wildcard
        handlers.current.get("*")?.forEach(fn => fn(msg));
      } catch { /* ignore parse errors */ }
    };

    socket.onclose = () => {
      setState(s => ({ ...s, connected: false }));
      if (pingTimer.current) clearInterval(pingTimer.current);
      const delay = Math.min(1000 * 2 ** retryCount.current, 30_000);
      retryCount.current += 1;
      retry.current = setTimeout(connect, delay);
    };

    socket.onerror = () => socket.close();
    ws.current = socket;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (retry.current)     clearTimeout(retry.current);
      ws.current?.close();
    };
  }, [connect]);

  const on = useCallback((type: WSMessageType | "*", fn: Handler) => {
    if (!handlers.current.has(type)) handlers.current.set(type, new Set());
    handlers.current.get(type)!.add(fn);
    return () => handlers.current.get(type)?.delete(fn);
  }, []);

  const send = useCallback((type: string, data: unknown = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN)
      ws.current.send(JSON.stringify({ type, data }));
  }, []);

  return { ...state, on, send };
}
