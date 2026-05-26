"use client";

/**
 * useAstraRuntime — Centralized runtime state for ASTRA OS.
 *
 * One hook, one polling interval, one source of truth.
 * Every component reads from this via AstraRuntimeContext.
 * Nothing polls independently. Zero duplicate fetches.
 *
 * Owns:
 *   - Sleep status polling (every 30s)
 *   - Background task unread count (every 10s)
 *   - Idle timer for auto-sleep
 *
 * Future (Commit 2 & 3 will extend):
 *   - Watcher directories status
 *   - Scheduler status
 */

import {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────

export interface SleepStatus {
  sleeping: boolean;
  model: string;
}

export interface AstraRuntimeState {
  // Sleep Mode
  sleepStatus: SleepStatus;
  sleepEnabled: boolean;
  sleepTimeoutMinutes: number;

  // Background Tasks
  taskRunsUnreadCount: number;
  lastTaskViewedAt: string | null;

  // Loading / error
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

// ── Reducer ────────────────────────────────────────────────────────

type Action =
  | { type: "SET_SLEEP_STATUS"; payload: SleepStatus }
  | { type: "SET_SLEEP_ENABLED"; payload: boolean }
  | { type: "SET_SLEEP_TIMEOUT"; payload: number }
  | { type: "SET_TASK_UNREAD_COUNT"; payload: number }
  | { type: "MARK_TASKS_VIEWED" }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null };

const initialState: AstraRuntimeState = {
  sleepStatus: { sleeping: false, model: "" },
  sleepEnabled: true,
  sleepTimeoutMinutes: 10,
  taskRunsUnreadCount: 0,
  lastTaskViewedAt: null,
  isLoading: false,
  error: null,
};

function runtimeReducer(state: AstraRuntimeState, action: Action): AstraRuntimeState {
  switch (action.type) {
    case "SET_SLEEP_STATUS":
      return { ...state, sleepStatus: action.payload };
    case "SET_SLEEP_ENABLED":
      return { ...state, sleepEnabled: action.payload };
    case "SET_SLEEP_TIMEOUT":
      return { ...state, sleepTimeoutMinutes: action.payload };
    case "SET_TASK_UNREAD_COUNT":
      return { ...state, taskRunsUnreadCount: action.payload };
    case "MARK_TASKS_VIEWED":
      return {
        ...state,
        taskRunsUnreadCount: 0,
        lastTaskViewedAt: new Date().toISOString(),
      };
    case "SET_LOADING":
      return { ...state, isLoading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────────────

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
  const [state, dispatch] = useReducer(runtimeReducer, initialState);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastActivityRef = useRef<number>(Date.now());

  // ── Fetch sleep status ─────────────────────────────────────────
  const fetchSleepStatus = useCallback(async () => {
    try {
      const status = await api.getSleepStatus();
      dispatch({ type: "SET_SLEEP_STATUS", payload: status });
    } catch {
      // Silently fail — backend may not have sleep endpoints yet (Pre-0)
    }
  }, []);

  // ── Fetch unread task count ────────────────────────────────────
  const fetchTaskCount = useCallback(async () => {
    try {
      const result = await api.getTaskRunCount(state.lastTaskViewedAt || undefined);
      dispatch({ type: "SET_TASK_UNREAD_COUNT", payload: result.count });
    } catch {
      // Silently fail
    }
  }, [state.lastTaskViewedAt]);

  // ── Refresh all state ──────────────────────────────────────────
  const refreshAll = useCallback(async () => {
    dispatch({ type: "SET_LOADING", payload: true });
    await Promise.allSettled([fetchSleepStatus(), fetchTaskCount()]);
    dispatch({ type: "SET_LOADING", payload: false });
  }, [fetchSleepStatus, fetchTaskCount]);

  // ── Sleep / Wake actions ───────────────────────────────────────
  const triggerSleep = useCallback(async () => {
    try {
      await api.sleepAgent();
      dispatch({
        type: "SET_SLEEP_STATUS",
        payload: { sleeping: true, model: state.sleepStatus.model },
      });
    } catch (e) {
      dispatch({ type: "SET_ERROR", payload: "Failed to sleep agent" });
    }
  }, [state.sleepStatus.model]);

  const triggerWake = useCallback(async () => {
    try {
      await api.wakeAgent();
      dispatch({
        type: "SET_SLEEP_STATUS",
        payload: { sleeping: false, model: state.sleepStatus.model },
      });
    } catch (e) {
      dispatch({ type: "SET_ERROR", payload: "Failed to wake agent" });
    }
  }, [state.sleepStatus.model]);

  // ── Settings actions ───────────────────────────────────────────
  const setSleepEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_SLEEP_ENABLED", payload: enabled });
  }, []);

  const setSleepTimeout = useCallback((minutes: number) => {
    dispatch({ type: "SET_SLEEP_TIMEOUT", payload: minutes });
  }, []);

  const markTasksViewed = useCallback(() => {
    dispatch({ type: "MARK_TASKS_VIEWED" });
  }, []);

  // ── Polling: single interval for everything ────────────────────
  useEffect(() => {
    // Initial fetch
    refreshAll();

    // Light polling: task count every 10s, sleep status every 30s
    let tick = 0;
    const interval = setInterval(() => {
      tick++;
      fetchTaskCount();                // Every 10s
      if (tick % 3 === 0) {
        fetchSleepStatus();            // Every 30s
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [refreshAll, fetchTaskCount, fetchSleepStatus]);

  // ── Idle timer for auto-sleep ──────────────────────────────────
  useEffect(() => {
    if (!state.sleepEnabled || state.sleepStatus.sleeping) return;

    const timeoutMs = state.sleepTimeoutMinutes * 60 * 1000;

    const resetTimer = () => {
      lastActivityRef.current = Date.now();
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
      idleTimerRef.current = setTimeout(() => {
        triggerSleep();
      }, timeoutMs);
    };

    // Listen for user activity
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
  }, [state.sleepEnabled, state.sleepTimeoutMinutes, state.sleepStatus.sleeping, triggerSleep]);

  // ── Context value ──────────────────────────────────────────────
  const value: AstraRuntime = {
    ...state,
    triggerSleep,
    triggerWake,
    refreshAll,
    setSleepEnabled,
    setSleepTimeout,
    markTasksViewed,
  };

  return (
    <AstraRuntimeContext.Provider value={value}>
      {children}
    </AstraRuntimeContext.Provider>
  );
}
