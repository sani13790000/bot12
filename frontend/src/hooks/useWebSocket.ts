import { useEffect, useRef, useCallback, useState } from "react";
import { WS_URL } from "../utils/config";

/**
 * FIX-FE4:  WSMessageType inline — was imported from types but did not exist
 * FIX-FE11: cleanup incomplete — socket stayed open after logout
 * FIX-FE12: unmounted guard — no setState after component unmounts
 * FIX-FE13: retryCount not reset on cleanup — caused reconnect storm
 */

type WSMessageType = string;
type Handler = (data: unknown) => void;

export interface WSState {
  connected: boolean;
  reconnecting: boolean;
  latency: number;
}

export function useWebSocket() {
  const ws         = useRef<WebSocket | null>(null);
  const handlers   = useRef<Map<WSMessageType, Set<Handler>>>(new Map());
  const pingTimer  = useRef<ReturnType<typeof setInterval> | null>(null);
  const pingTs     = useRef<number>(0);
  const retry      = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount = useRef(0);
  const unmounted  = useRef(false);

  const [state, setState] = useState<WSState>({
    connected: false, reconnecting: false, latency: 0,
  });

  const cleanup = useCallback(() => {
    if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
    if (retry.current)     { clearTimeout(retry.current);     retry.current = null; }
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (unmounted.current) return;
    if (ws.current?.readyState === WebSocket.OPEN) return;
    setState(s => ({ ...s, reconnecting: retryCount.current > 0 }));
    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      if (unmounted.current) { socket.close(); return; }
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
        const msg = JSON.parse(ev.data as string);
        if (msg.type === "PONG") {
          setState(s => ({ ...s, latency: Date.now() - pingTs.current }));
          return;
        }
        handlers.current.get(msg.type)?.forEach(fn => fn(msg.data));
        handlers.current.get("*")?.forEach(fn => fn(msg));
      } catch { /* ignore parse errors */ }
    };

    socket.onclose = () => {
      if (unmounted.current) return;
      setState(s => ({ ...s, connected: false }));
      if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
      const delay = Math.min(1000 * 2 ** retryCount.current, 30_000);
      retryCount.current += 1;
      retry.current = setTimeout(connect, delay);
    };

    socket.onerror = () => socket.close();
    ws.current = socket;
  }, []);

  useEffect(() => {
    unmounted.current = false;
    connect();
    return () => {
      unmounted.current = true;
      cleanup();
    };
  }, [connect, cleanup]);

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
