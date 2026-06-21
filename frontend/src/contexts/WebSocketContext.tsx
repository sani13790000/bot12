/**
 * frontend/src/contexts/WebSocketContext.tsx
 *
 * FIX-E2: WebSocketContext وجود نداشت — App.tsx آن را import می‌کرد → build fail
 */
import React, {
  createContext, useContext, useEffect, useRef,
  useState, useCallback, type ReactNode,
} from "react";

interface PriceData {
  symbol: string;
  bid: number;
  ask: number;
  timestamp: string;
}

interface SignalData {
  id: string;
  symbol: string;
  direction: "BUY" | "SELL" | "NEUTRAL";
  confidence: number;
  created_at: string;
}

type WSMessage =
  | { type: "price"; symbol: string; data: PriceData }
  | { type: "signal"; data: SignalData }
  | { type: "heartbeat"; ts: number }
  | { type: "ping" }
  | { type: "error"; message: string };

interface WebSocketContextValue {
  isConnected: boolean;
  lastPrice: Record<string, PriceData>;
  lastSignal: SignalData | null;
  subscribePrice: (symbol: string) => void;
  unsubscribePrice: (symbol: string) => void;
}

const ALLOWED_SYMBOLS = new Set([
  "XAUUSD","EURUSD","GBPUSD","USDJPY","USDCHF",
  "AUDUSD","USDCAD","NZDUSD","GBPJPY","EURJPY",
  "EURGBP","XAGUSD","BTCUSD","ETHUSD",
]);

const BASE_URL = (import.meta.env?.VITE_API_URL as string | undefined) || "http://localhost:8000";
const WS_BASE  = BASE_URL.replace(/^http/, "ws");

const WebSocketContext = createContext<WebSocketContextValue>({
  isConnected: false, lastPrice: {}, lastSignal: null,
  subscribePrice: () => undefined, unsubscribePrice: () => undefined,
});

export function useWebSocket(): WebSocketContextValue {
  return useContext(WebSocketContext);
}

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastPrice,   setLastPrice]   = useState<Record<string, PriceData>>({});
  const [lastSignal,  setLastSignal]  = useState<SignalData | null>(null);

  const priceWsRef    = useRef<WebSocket | null>(null);
  const signalWsRef   = useRef<WebSocket | null>(null);
  const reconnectRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef    = useRef(1_000);
  const mountedRef    = useRef(true);

  const getToken = (): string | null => localStorage.getItem("gv_token");

  const connectPrice = useCallback((symbol: string) => {
    const token = getToken();
    if (!token || !ALLOWED_SYMBOLS.has(symbol.toUpperCase())) return;
    priceWsRef.current?.close();
    const url = `${WS_BASE}/ws/prices?token=${encodeURIComponent(token)}&symbol=${encodeURIComponent(symbol)}`;
    const ws  = new WebSocket(url);
    priceWsRef.current = ws;
    ws.onopen    = () => { if (mountedRef.current) { setIsConnected(true); backoffRef.current = 1_000; } };
    ws.onmessage = (evt) => {
      if (!mountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(evt.data as string);
        if (msg.type === "price") setLastPrice(p => ({ ...p, [msg.symbol]: msg.data }));
        else if (msg.type === "ping") ws.send(JSON.stringify({ type: "pong" }));
      } catch { /* ignore */ }
    };
    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = setTimeout(() => {
        if (mountedRef.current) { connectPrice(symbol); backoffRef.current = Math.min(backoffRef.current * 2, 30_000); }
      }, backoffRef.current);
    };
    ws.onerror = () => ws.close();
  }, []);

  const connectSignals = useCallback(() => {
    const token = getToken();
    if (!token) return;
    signalWsRef.current?.close();
    const ws = new WebSocket(`${WS_BASE}/ws/signals?token=${encodeURIComponent(token)}`);
    signalWsRef.current = ws;
    ws.onmessage = (evt) => {
      if (!mountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(evt.data as string);
        if (msg.type === "signal") setLastSignal(msg.data);
      } catch { /* ignore */ }
    };
    ws.onclose = () => { if (mountedRef.current) setTimeout(connectSignals, backoffRef.current); };
  }, []);

  const subscribePrice   = useCallback((symbol: string) => {
    if (ALLOWED_SYMBOLS.has(symbol.toUpperCase())) connectPrice(symbol.toUpperCase());
  }, [connectPrice]);

  const unsubscribePrice = useCallback((_symbol: string) => {
    priceWsRef.current?.close();
    priceWsRef.current = null;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const token = getToken();
    if (token) { connectSignals(); connectPrice("XAUUSD"); }
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      priceWsRef.current?.close();
      signalWsRef.current?.close();
    };
  }, [connectPrice, connectSignals]);

  return (
    <WebSocketContext.Provider value={{ isConnected, lastPrice, lastSignal, subscribePrice, unsubscribePrice }}>
      {children}
    </WebSocketContext.Provider>
  );
}
