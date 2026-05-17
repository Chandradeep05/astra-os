"use client";

import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ASTRA OS Component Crash:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-full p-12 text-center space-y-6">
          <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <AlertCircle size={32} className="text-red-500" />
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-bold text-white">Module Crash Detected</h3>
            <p className="text-sm text-zinc-500 max-w-md">
              A component encountered an unrecoverable error. This is isolated — the rest of ASTRA OS is still operational.
            </p>
            {this.state.error && (
              <p className="text-xs text-red-400/60 font-mono mt-2 p-3 bg-red-500/5 rounded-xl border border-red-500/10">
                {this.state.error.message}
              </p>
            )}
          </div>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
            }}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-white/5 border border-white/10 text-white text-xs font-bold uppercase tracking-widest hover:bg-white/10 transition-all"
          >
            <RefreshCw size={14} />
            Retry Module
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
