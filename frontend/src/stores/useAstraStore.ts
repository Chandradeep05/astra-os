"use client";

import { create } from "zustand";
import { api } from "@/lib/api";

/* ══════════════════════════════════════════════════════════════════════
   ASTRA OS — Global Store (Zustand)
   
   Single source of truth for:
   - Navigation state
   - Environmental state (atmosphere)
   - Sleep/wake status
   - Runtime telemetry
   - Boot state
   - Command palette state
   - Right panel state
   ══════════════════════════════════════════════════════════════════════ */

// ── Types ────────────────────────────────────────────────────────────

export type EnvironmentState =
  | "idle"
  | "thinking"
  | "executing"
  | "warning"
  | "sleeping"
  | "error";

export type ActiveView =
  | "dashboard"
  | "agent"
  | "memory-browser"
  | "documents"
  | "tasks"
  | "settings"
  | "scheduled-tasks"
  | string; // project IDs are dynamic strings

export interface SleepStatus {
  sleeping: boolean;
  model: string;
}

export interface RuntimeTelemetry {
  ollama_status: string;
  model_name: string;
  documents_indexed: number;
  episodic_memories: number;
  ram_usage_percent: number;
  cpu_percent: number;
}

export interface AstraStore {
  // ── Navigation ──────────────────────────────────────────────────
  activeView: ActiveView;
  activeProjectName: string;
  currentProjectContext: string;
  sidebarCollapsed: boolean;
  setActiveView: (view: ActiveView, label?: string) => void;
  toggleSidebar: () => void;

  // ── Right Panel ─────────────────────────────────────────────────
  rightPanelOpen: boolean;
  toggleRightPanel: () => void;

  // ── Command Palette ─────────────────────────────────────────────
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
  toggleCommandPalette: () => void;

  // ── Boot State ──────────────────────────────────────────────────
  booted: boolean;
  setBooted: (booted: boolean) => void;

  // ── Environmental State ─────────────────────────────────────────
  environmentState: EnvironmentState;
  setEnvironmentState: (state: EnvironmentState) => void;

  // ── Sleep/Wake ──────────────────────────────────────────────────
  sleepStatus: SleepStatus;
  sleepEnabled: boolean;
  sleepTimeoutMinutes: number;
  triggerSleep: () => Promise<void>;
  triggerWake: () => Promise<void>;
  setSleepEnabled: (enabled: boolean) => void;
  setSleepTimeout: (minutes: number) => void;

  // ── Background Tasks ────────────────────────────────────────────
  taskRunsUnreadCount: number;
  lastTaskViewedAt: string | null;
  markTasksViewed: () => void;

  // ── Runtime Telemetry ───────────────────────────────────────────
  telemetry: RuntimeTelemetry;

  // ── Polling Actions ─────────────────────────────────────────────
  fetchSleepStatus: () => Promise<void>;
  fetchTaskCount: () => Promise<void>;
  fetchTelemetry: () => Promise<void>;
  refreshAll: () => Promise<void>;

  // ── Loading / Error ─────────────────────────────────────────────
  isLoading: boolean;
  error: string | null;
}

// ── Virtual Views (non-project pages) ────────────────────────────

const VIRTUAL_VIEWS = [
  "dashboard",
  "agent",
  "memory-browser",
  "documents",
  "tasks",
  "settings",
  "scheduled-tasks",
];

// ── Store Creation ──────────────────────────────────────────────────

export const useAstraStore = create<AstraStore>((set, get) => ({
  // ── Navigation ──────────────────────────────────────────────────
  activeView: "dashboard",
  activeProjectName: "Dashboard",
  currentProjectContext: "default",
  sidebarCollapsed: true,
  setActiveView: (view, label) => {
    set({
      activeView: view,
      activeProjectName: label || view,
    });
    // Preserve project context when switching to virtual views
    if (!VIRTUAL_VIEWS.includes(view)) {
      set({ currentProjectContext: view });
    }
  },
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  // ── Right Panel ─────────────────────────────────────────────────
  rightPanelOpen: false,
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),

  // ── Command Palette ─────────────────────────────────────────────
  commandPaletteOpen: false,
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
  toggleCommandPalette: () =>
    set((s) => ({ commandPaletteOpen: !s.commandPaletteOpen })),

  // ── Boot State ──────────────────────────────────────────────────
  // Always false initially — BootSequence's useEffect handles the
  // sessionStorage check client-side and calls setBooted(true) via onComplete.
  // This avoids hydration mismatch (server vs client sessionStorage divergence).
  booted: false,
  setBooted: (booted) => set({ booted }),

  // ── Environmental State ─────────────────────────────────────────
  environmentState: "idle",
  setEnvironmentState: (environmentState) => set({ environmentState }),

  // ── Sleep/Wake ──────────────────────────────────────────────────
  sleepStatus: { sleeping: false, model: "" },
  sleepEnabled: true,
  sleepTimeoutMinutes: 10,
  triggerSleep: async () => {
    try {
      await api.sleepAgent();
      set((s) => ({
        sleepStatus: { sleeping: true, model: s.sleepStatus.model },
        environmentState: "sleeping",
      }));
    } catch {
      set({ error: "Failed to sleep agent" });
    }
  },
  triggerWake: async () => {
    try {
      await api.wakeAgent();
      set((s) => ({
        sleepStatus: { sleeping: false, model: s.sleepStatus.model },
        environmentState: "idle",
      }));
    } catch {
      set({ error: "Failed to wake agent" });
    }
  },
  setSleepEnabled: (sleepEnabled) => set({ sleepEnabled }),
  setSleepTimeout: (sleepTimeoutMinutes) => set({ sleepTimeoutMinutes }),

  // ── Background Tasks ────────────────────────────────────────────
  taskRunsUnreadCount: 0,
  lastTaskViewedAt: null,
  markTasksViewed: () =>
    set({
      taskRunsUnreadCount: 0,
      lastTaskViewedAt: new Date().toISOString(),
    }),

  // ── Runtime Telemetry ───────────────────────────────────────────
  telemetry: {
    ollama_status: "disconnected",
    model_name: "none",
    documents_indexed: 0,
    episodic_memories: 0,
    ram_usage_percent: 0,
    cpu_percent: 0,
  },

  // ── Polling Actions ─────────────────────────────────────────────
  fetchSleepStatus: async () => {
    try {
      const status = await api.getSleepStatus();
      set({ sleepStatus: status });
      if (status.sleeping && get().environmentState !== "sleeping") {
        set({ environmentState: "sleeping" });
      }
    } catch {
      // Silently fail — backend may not have sleep endpoints
    }
  },
  fetchTaskCount: async () => {
    try {
      const { lastTaskViewedAt } = get();
      const result = await api.getTaskRunCount(
        lastTaskViewedAt || undefined
      );
      set({ taskRunsUnreadCount: result.count });
    } catch {
      // Silently fail
    }
  },
  fetchTelemetry: async () => {
    try {
      const stats = await api.getStats();
      set({ telemetry: stats });
    } catch {
      // Silently fail
    }
  },
  refreshAll: async () => {
    set({ isLoading: true });
    const { fetchSleepStatus, fetchTaskCount, fetchTelemetry } = get();
    await Promise.allSettled([
      fetchSleepStatus(),
      fetchTaskCount(),
      fetchTelemetry(),
    ]);
    set({ isLoading: false });
  },

  // ── Loading / Error ─────────────────────────────────────────────
  isLoading: false,
  error: null,
}));
