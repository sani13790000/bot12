import { useWS } from "../../contexts/WebSocketContext";

export function WSIndicator() {
  const { connected, reconnecting, latency } = useWS();
  if (reconnecting) return (
    <div className="flex items-center gap-1.5 text-xs text-[#f59e0b]">
      <span className="w-2 h-2 rounded-full bg-[#f59e0b] animate-pulse" />
      اتصال مجدد...
    </div>
  );
  return (
    <div className={`flex items-center gap-1.5 text-xs ${connected ? "text-[#10b981]" : "text-[#ef4444]"}`}>
      <span className={`w-2 h-2 rounded-full ${connected ? "bg-[#10b981]" : "bg-[#ef4444]"} ${connected ? "animate-pulse" : ""}`} />
      {connected ? `Live${latency > 0 ? ` · ${latency}ms` : ""}` : "آفلاین"}
    </div>
  );
}
