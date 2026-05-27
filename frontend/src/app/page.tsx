"use client";

import React, { useEffect, useMemo } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatInterface } from "@/components/ChatInterface";
import { AstraAgent } from "@/components/AstraAgent";
import { Dashboard } from "@/components/Dashboard";
import { MemoryBrowser } from "@/components/MemoryBrowser";
import { DocumentManager } from "@/components/DocumentManager";
import { SettingsPanel } from "@/components/SettingsPanel";
import { BackgroundTasks } from "@/components/BackgroundTasks";
import { ScheduledTasks } from "@/components/ScheduledTasks";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AstraRuntimeProvider } from "@/hooks/useAstraRuntime";
import { BootSequence } from "@/components/BootSequence";
import { CommandDock } from "@/components/CommandDock";
import { RightPanel } from "@/components/RightPanel";
import { useAstraStore } from "@/stores/useAstraStore";
import { AnimatePresence, motion } from "framer-motion";

/* ══════════════════════════════════════════════════════════════════════
   ASTRA OS — Application Shell
   
   Layout:
   ┌────────┬──────────────────────────┬────────────┐
   │  LEFT  │      CENTER VIEWPORT     │   RIGHT    │
   │  NAV   │                          │   PANEL    │
   │  RAIL  │                          │  (hidden)  │
   ├────────┴──────────────────────────┴────────────┤
   │                 COMMAND DOCK                    │
   └─────────────────────────────────────────────────┘
   
   Wrapped in:
   - BootSequence overlay (plays once per session)
   - AstraRuntimeProvider (backward-compat Context)
   - Environmental state (atmosphere CSS vars)
   ══════════════════════════════════════════════════════════════════════ */

// ── Environmental state → CSS variable map ──────────────────────────

const ENV_STYLES: Record<
  string,
  { glowOpacity: string; glowColor: string; gridOpacity: string; driftSpeed: string }
> = {
  idle: { glowOpacity: "0.04", glowColor: "#06b6d4", gridOpacity: "0.03", driftSpeed: "16s" },
  thinking: { glowOpacity: "0.08", glowColor: "#06b6d4", gridOpacity: "0.05", driftSpeed: "8s" },
  executing: { glowOpacity: "0.15", glowColor: "#06b6d4", gridOpacity: "0.06", driftSpeed: "4s" },
  warning: { glowOpacity: "0.10", glowColor: "#f59e0b", gridOpacity: "0.04", driftSpeed: "6s" },
  sleeping: { glowOpacity: "0.02", glowColor: "#8b5cf6", gridOpacity: "0.02", driftSpeed: "30s" },
  error: { glowOpacity: "0.08", glowColor: "#ef4444", gridOpacity: "0.03", driftSpeed: "16s" },
};

// ── View transition variants ────────────────────────────────────────

const viewTransition = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.3, ease: "easeOut" as const },
};

export default function Home() {
  const {
    activeView,
    activeProjectName,
    currentProjectContext,
    setActiveView,
    environmentState,
    booted,
    setBooted,
  } = useAstraStore();

  const handleSelectProject = (id: string, label?: string) => {
    setActiveView(id, label);
  };

  // ── Environmental CSS vars ────────────────────────────────────

  const envStyle = useMemo(() => {
    const e = ENV_STYLES[environmentState] || ENV_STYLES.idle;
    return {
      "--env-glow-opacity": e.glowOpacity,
      "--env-glow-color": e.glowColor,
      "--env-grid-opacity": e.gridOpacity,
      "--env-drift-speed": e.driftSpeed,
    } as React.CSSProperties;
  }, [environmentState]);

  return (
    <AstraRuntimeProvider>
      <BootSequence onComplete={() => setBooted(true)}>
        <div
          className="flex flex-col w-full h-screen bg-[var(--color-base)] overflow-hidden relative"
          style={envStyle}
        >
          {/* ── Environmental Glow Orbs ─────────────────────────── */}
          <div className="env-glow w-[400px] h-[400px] -top-[200px] -right-[100px]" />
          <div className="env-glow w-[320px] h-[320px] -bottom-[150px] -left-[100px]" />

          {/* ── Background Grid ────────────────────────────────── */}
          <div className="absolute inset-0 bg-grid pointer-events-none" />

          {/* ── Main Layout (Sidebar + Viewport + RightPanel) ── */}
          <div className="flex flex-1 min-h-0 relative z-10">
            {/* Left Rail */}
            <Sidebar
              activeProject={activeView}
              onSelectProject={handleSelectProject}
            />

            {/* Center Viewport */}
            <main className="flex-1 min-w-0 relative overflow-hidden">
              <AnimatePresence mode="wait">
                {activeView === "dashboard" ? (
                  <motion.div
                    key="dashboard"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <Dashboard onSelectProject={handleSelectProject} />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "agent" ? (
                  <motion.div
                    key="agent"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <AstraAgent />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "memory-browser" ? (
                  <motion.div
                    key="memory-browser"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <MemoryBrowser />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "documents" ? (
                  <motion.div
                    key="documents"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <DocumentManager projectId={currentProjectContext} />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "tasks" ? (
                  <motion.div
                    key="tasks"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <BackgroundTasks projectId={currentProjectContext} />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "settings" ? (
                  <motion.div
                    key="settings"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <SettingsPanel />
                    </ErrorBoundary>
                  </motion.div>
                ) : activeView === "scheduled-tasks" ? (
                  <motion.div
                    key="scheduled-tasks"
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <ScheduledTasks />
                    </ErrorBoundary>
                  </motion.div>
                ) : (
                  <motion.div
                    key={activeView}
                    {...viewTransition}
                    className="h-full w-full"
                  >
                    <ErrorBoundary>
                      <ChatInterface
                        project_id={activeView}
                        project_name={activeProjectName}
                      />
                    </ErrorBoundary>
                  </motion.div>
                )}
              </AnimatePresence>
            </main>

            {/* Right Context Panel */}
            <RightPanel />
          </div>

          {/* ── Command Dock (Bottom Bar) ──────────────────────── */}
          <CommandDock />
        </div>
      </BootSequence>
    </AstraRuntimeProvider>
  );
}
