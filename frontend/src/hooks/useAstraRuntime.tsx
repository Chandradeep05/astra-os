"use client";

/**
 * useAstraRuntime — Backward-compatible wrapper over Zustand store.
 *
 * All existing components that import `useAstraRuntime()` or
 * `<AstraRuntimeProvider>` continue working without changes.
 *
 * Internally delegates to `useAstraStore` for all state.
 */

import {
  createContext,
  useContext,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { useAstraStore } from "@/stores/useAstraStore";

// ── Types (preserved for backward compat) ──────────────────────────

export interface SleepStatus {
  sleeping: boolean;
  model: string;
}

export interface AstraRuntimeState {
  sleepStatus: SleepStatus;
  sleepEnabled: boolean;
  sleepTimeoutMinutes: number;
  taskRunsUnreadCount: number;
  lastTaskViewedAt: string | null;
  isLoading: boolean;
  error: string | null;
}

interface AstraRuntimeActions {
  triggerSleep: () => Promise<void>;
  triggerWake: () => Promise<void>;
  refreshAll: () => Promise<void>;
  setSleepEnabled: (enabled: boolean) => void;
  setSleepTimeout: (minutes: number) => void;
  markTasksViewed: () => void;
}

export type AstraRuntime = AstraRuntimeState & AstraRuntimeActions;

// ── Context (backward compat — components can still useContext) ─────

const AstraRuntimeContext = createContext<AstraRuntime | null>(null);

export function useAstraRuntime(): AstraRuntime {
  const ctx = useContext(AstraRuntimeContext);
  if (!ctx) {
    throw new Error("useAstraRuntime must be used within <AstraRuntimeProvider>");
  }
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────

interface ProviderProps {
  children: ReactNode;
}

export function AstraRuntimeProvider({ children }: ProviderProps) {
  const store = useAstraStore();
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Polling: single interval for everything ────────────────────
  useEffect(() => {
    // Initial fetch
    store.refreshAll();

    // Light polling: task count every 10s, sleep+telemetry every 30s
    let tick = 0;
    const interval = setInterval(() => {
      tick++;
      store.fetchTaskCount(); // Every 10s
      if (tick % 3 === 0) {
        store.fetchSleepStatus(); // Every 30s
        store.fetchTelemetry(); // Every 30s
      }
    }, 10000);

    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Idle timer for auto-sleep ──────────────────────────────────
  useEffect(() => {
    if (!store.sleepEnabled || store.sleepStatus.sleeping) return;

    const timeoutMs = store.sleepTimeoutMinutes * 60 * 1000;

    const resetTimer = () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
      idleTimerRef.current = setTimeout(() => {
        store.triggerSleep();
      }, timeoutMs);
    };

    window.addEventListener("keydown", resetTimer);
    window.addEventListener("mousedown", resetTimer);
    window.addEventListener("touchstart", resetTimer);
    resetTimer();

    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      window.removeEventListener("keydown", resetTimer);
      window.removeEventListener("mousedown", resetTimer);
      window.removeEventListener("touchstart", resetTimer);
    };
  }, [store.sleepEnabled, store.sleepTimeoutMinutes, store.sleepStatus.sleeping]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Build context value from store ─────────────────────────────
  const value: AstraRuntime = {
    sleepStatus: store.sleepStatus,
    sleepEnabled: store.sleepEnabled,
    sleepTimeoutMinutes: store.sleepTimeoutMinutes,
    taskRunsUnreadCount: store.taskRunsUnreadCount,
    lastTaskViewedAt: store.lastTaskViewedAt,
    isLoading: store.isLoading,
    error: store.error,
    triggerSleep: store.triggerSleep,
    triggerWake: store.triggerWake,
    refreshAll: store.refreshAll,
    setSleepEnabled: store.setSleepEnabled,
    setSleepTimeout: store.setSleepTimeout,
    markTasksViewed: store.markTasksViewed,
  };

  return (
    <AstraRuntimeContext.Provider value={value}>
      {children}
    </AstraRuntimeContext.Provider>
  );
}
