import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Operator console render failed", error, info.componentStack);
  }
  render() {
    return this.state.failed ? (
      <main className="error-boundary">
        <h1>Operator console failed to render.</h1>
        <p>The scientific backend remains unaffected.</p>
      </main>
    ) : (
      this.props.children
    );
  }
}
