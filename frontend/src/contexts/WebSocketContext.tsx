import { createContext, useContext, ReactNode } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

type WSContextType = ReturnType<typeof useWebSocket>;
const WebSocketContext = createContext<WSContextType | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const ws = useWebSocket();
  return <WebSocketContext.Provider value={ws}>{children}</WebSocketContext.Provider>;
}

export function useWS() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWS must be used inside WebSocketProvider");
  return ctx;
}
