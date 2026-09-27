import { AlertTriangle } from "@/components/icons";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this value clears the error and renders the children again. */
  resetKey?: unknown;
  label?: string;
}

/** Keeps one broken widget from blanking the whole screen. */
export class ErrorBoundary extends Component<Props, { error: Error | null; key: unknown }> {
  state = { error: null as Error | null, key: this.props.resetKey };

  static getDerivedStateFromProps(props: Props, state: { error: Error | null; key: unknown }) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="glass-dense flex items-start gap-2.5 rounded-2xl px-3.5 py-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" />
        <div>
          <p className="font-semibold">{this.props.label ?? "Something went wrong showing this."}</p>
          <p className="text-xs text-ink-3">Your data is safe. Reload the page if this keeps happening.</p>
        </div>
      </div>
    );
  }
}
