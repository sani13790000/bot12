import { useWS } from "../../contexts/WebSocketContext";
import { Wifi, WifiOff } from "lucide-react";

export function WSIndicator() {
  const { connected, lastPing } = useWS();
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#0d1420] border border-[#1e2d40]">
      {connected ? (
        <>
          <span className="w-2 h-2 rounded-full bg-[#10b981] pulse-dot" />
          <Wifi size={13} className="text-[#10b981]" />
          <span className="text-[10px] text-[#10b981] font-mono">LIVE</span>
        </>
      ) : (
        <>
          <span className="w-2 h-2 rounded-full bg-[#ef4444]" />
          <WifiOff size={13} className="text-[#ef4444]" />
          <span className="text-[10px] text-[#ef4444] font-mono">OFF</span>
        </>
      )}
      {lastPing && (
        <span className="text-[9px] text-[#475569] font-mono hidden sm:block">
          {lastPing.toLocaleTimeString("fa")}
        </span>
      )}
    </div>
  );
}
