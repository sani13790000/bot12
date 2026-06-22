/**
 * frontend/src/components/common/ErrorBoundary.tsx
 * FIX-23: هیچ ErrorBoundary وجود نداشت — crash → white screen
 * FIX-24: withErrorBoundary HOC
 */
import { Component, type ReactNode, type ErrorInfo } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";

interface Props { children: ReactNode; message?: string; onError?: (error: Error, info: ErrorInfo) => void; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) { super(props); this.state = { hasError: false, error: null }; }

  static getDerivedStateFromError(error: Error): State { return { hasError: true, error }; }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  private reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex flex-col items-center justify-center min-h-[300px] p-8 text-center">
        <div className="w-14 h-14 rounded-full bg-red-900/30 flex items-center justify-center mb-4">
          <AlertTriangle className="w-7 h-7 text-red-400" />
        </div>
        <h2 className="text-lg font-semibold text-white mb-2">{this.props.message ?? "خطایی رخ داد"}</h2>
        <p className="text-gray-400 text-sm mb-6 max-w-sm">{this.state.error?.message ?? "خطای ناشناخته"}</p>
        <button onClick={this.reset}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm transition-colors">
          <RefreshCw className="w-4 h-4" />تلاش مجدد
        </button>
      </div>
    );
  }
}

export function withErrorBoundary<P extends object>(WrappedComponent: React.ComponentType<P>, message?: string) {
  const displayName = WrappedComponent.displayName ?? WrappedComponent.name ?? "Component";
  function WithErrorBoundary(props: P) {
    return <ErrorBoundary message={message}><WrappedComponent {...props} /></ErrorBoundary>;
  }
  WithErrorBoundary.displayName = `withErrorBoundary(${displayName})`;
  return WithErrorBoundary;
}
