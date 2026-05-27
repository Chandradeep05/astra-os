"use client";

import React from "react";
import {
  X,
  Cpu,
  Database,
  Activity,
  FileText,
  Clock,
  Layers,
  Moon,
  Eye,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAstraStore } from "@/stores/useAstraStore";
import { StatusDot } from "@/components/ui/StatusDot";
import { SystemLabel } from "@/components/ui/SystemLabel";

/* ══════════════════════════════════════════════════════════════════════
   RIGHT PANEL — Context Intelligence Sidebar
   
   Collapsible. Always collapsed by default.
   Toggle with Cmd+. or explicit button.
   Shows context-aware intelligence based on active view.
   ══════════════════════════════════════════════════════════════════════ */

export const RightPanel = () => {
  const {
    rightPanelOpen,
    toggleRightPanel,
    activeView,
    telemetry,
    sleepStatus,
    taskRunsUnreadCount,
    environmentState,
  } = useAstraStore();

  // ── Global Cmd+. shortcut ─────────────────────────────────────

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ".") {
        e.preventDefault();
        toggleRightPanel();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleRightPanel]);

  return (
    <AnimatePresence>
      {rightPanelOpen && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 320, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: "easeInOut" }}
          className="h-full border-l border-[var(--color-border-subtle)] bg-[var(--color-void)]/90 backdrop-blur-xl overflow-hidden flex flex-col shrink-0"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-[var(--color-border-subtle)]">
            <SystemLabel size="xs" icon={<Eye size={12} />}>
              Context Intelligence
            </SystemLabel>
            <button
              onClick={toggleRightPanel}
              className="p-1.5 rounded-lg hover:bg-white/5 text-[var(--color-text-muted)] hover:text-[var(--color-text-body)] transition-colors duration-[var(--motion-hover)]"
            >
              <X size={14} />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-hide">
            {/* System Status — always visible (critical info) */}
            <section className="space-y-3">
              <SystemLabel size="xs" color="cyan" icon={<Cpu size={10} />}>
                System Status
              </SystemLabel>
              <div className="space-y-2">
                <StatusRow
                  label="Neural Engine"
                  value={telemetry.ollama_status === "connected" ? "Online" : "Offline"}
                  status={telemetry.ollama_status === "connected" ? "online" : "offline"}
                />
                <StatusRow
                  label="Active Model"
                  value={telemetry.model_name !== "none" ? telemetry.model_name : "—"}
                  mono
                />
                <StatusRow
                  label="Environment"
                  value={environmentState.toUpperCase()}
                  status={
                    environmentState === "idle"
                      ? "online"
                      : environmentState === "sleeping"
                      ? "sleeping"
                      : environmentState === "executing"
                      ? "executing"
                      : environmentState === "thinking"
                      ? "thinking"
                      : environmentState === "warning"
                      ? "warning"
                      : environmentState === "error"
                      ? "error"
                      : "online"
                  }
                />
                {sleepStatus.sleeping && (
                  <StatusRow label="Sleep Mode" value="Active" status="sleeping" />
                )}
              </div>
            </section>

            {/* Telemetry */}
            <section className="space-y-3">
              <SystemLabel size="xs" color="purple" icon={<Activity size={10} />}>
                Telemetry
              </SystemLabel>
              <div className="space-y-2">
                <MetricRow
                  icon={<Activity size={12} />}
                  label="CPU Load"
                  value={`${telemetry.cpu_percent.toFixed(1)}%`}
                  percent={telemetry.cpu_percent}
                  color="cyan"
                />
                <MetricRow
                  icon={<Layers size={12} />}
                  label="RAM Usage"
                  value={`${telemetry.ram_usage_percent.toFixed(1)}%`}
                  percent={telemetry.ram_usage_percent}
                  color="purple"
                />
              </div>
            </section>

            {/* Context-Aware Section — changes based on activeView */}
            <section className="space-y-3">
              <SystemLabel size="xs" color="emerald" icon={<Database size={10} />}>
                {activeView === "agent" ? "Agent Context" :
                 activeView === "memory-browser" ? "Memory Stats" :
                 "Knowledge"}
              </SystemLabel>

              {activeView === "agent" ? (
                <div className="space-y-2">
                  <StatusRow
                    label="OODA Phase"
                    value={environmentState === "executing" ? "Active" : "Standby"}
                    status={environmentState === "executing" ? "executing" : "online"}
                  />
                  <StatusRow
                    label="Stream"
                    value={environmentState === "executing" ? "SSE Connected" : "Idle"}
                    mono
                  />
                </div>
              ) : activeView === "memory-browser" ? (
                <div className="space-y-2">
                  <StatCard
                    icon={<Database size={14} />}
                    value={telemetry.episodic_memories}
                    label="Episodes"
                  />
                  <StatusRow
                    label="Storage"
                    value="SQLite + ChromaDB"
                    mono
                  />
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  <StatCard
                    icon={<FileText size={14} />}
                    value={telemetry.documents_indexed}
                    label="Documents"
                  />
                  <StatCard
                    icon={<Database size={14} />}
                    value={telemetry.episodic_memories}
                    label="Memories"
                  />
                </div>
              )}
            </section>

            {/* Active Tasks */}
            {taskRunsUnreadCount > 0 && (
              <section className="space-y-3">
                <SystemLabel size="xs" color="amber" icon={<Clock size={10} />}>
                  Pending
                </SystemLabel>
                <div className="glass-surface rounded-xl p-3 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[var(--color-warning)]/10 flex items-center justify-center">
                    <Activity size={14} className="text-[var(--color-warning)]" />
                  </div>
                  <div>
                    <p className="text-[12px] font-semibold text-[var(--color-text-bright)]">
                      {taskRunsUnreadCount} unread task{taskRunsUnreadCount !== 1 ? "s" : ""}
                    </p>
                    <p className="text-[10px] text-[var(--color-text-muted)]">
                      Since last viewed
                    </p>
                  </div>
                </div>
              </section>
            )}

            {/* Keyboard Shortcuts */}
            <section className="space-y-3 pt-4 border-t border-[var(--color-border-subtle)]">
              <SystemLabel size="xs" icon={<Activity size={10} />}>
                Shortcuts
              </SystemLabel>
              <div className="space-y-1.5">
                <ShortcutRow keys={["⌘", "K"]} label="Command Palette" />
                <ShortcutRow keys={["⌘", "."]} label="Context Panel" />
                <ShortcutRow keys={["⌘", "1-6"]} label="Quick Navigation" />
                <ShortcutRow keys={["⌘", "/"]} label="Focus Search" />
                <ShortcutRow keys={["⌘", "⏎"]} label="Send Message" />
                <ShortcutRow keys={["ESC"]} label="Close Overlays" />
              </div>
            </section>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
};

// ── Sub-components ──────────────────────────────────────────────────

const StatusRow = ({
  label,
  value,
  status,
  mono,
}: {
  label: string;
  value: string;
  status?: React.ComponentProps<typeof StatusDot>["status"];
  mono?: boolean;
}) => (
  <div className="flex items-center justify-between py-1.5">
    <span className="text-[11px] text-[var(--color-text-muted)]">{label}</span>
    <div className="flex items-center gap-2">
      {status && <StatusDot status={status} size="sm" pulse={false} />}
      <span
        className={cn(
          "text-[11px] font-semibold text-[var(--color-text-body)]",
          mono && "font-terminal"
        )}
      >
        {value}
      </span>
    </div>
  </div>
);

const MetricRow = ({
  icon,
  label,
  value,
  percent,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  percent: number;
  color: "cyan" | "purple" | "emerald";
}) => {
  const barColor = {
    cyan: "bg-[var(--color-accent-cyan)]",
    purple: "bg-[var(--color-accent-purple)]",
    emerald: "bg-[var(--color-success)]",
  };
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
          {icon}
          {label}
        </span>
        <span className="text-[11px] font-semibold font-terminal text-[var(--color-text-body)]">
          {value}
        </span>
      </div>
      <div className="h-1 w-full bg-[var(--color-surface)] rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-1000", barColor[color])}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
};

const StatCard = ({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
}) => (
  <div className="glass-surface rounded-xl p-3 space-y-1">
    <span className="text-[var(--color-text-muted)]">{icon}</span>
    <p className="text-lg font-bold text-[var(--color-text-bright)]">{value}</p>
    <p className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">
      {label}
    </p>
  </div>
);

const ShortcutRow = ({ keys, label }: { keys: string[]; label: string }) => (
  <div className="flex items-center justify-between py-1">
    <span className="text-[10px] text-[var(--color-text-muted)]">{label}</span>
    <div className="flex items-center gap-1">
      {keys.map((key) => (
        <kbd
          key={key}
          className="px-1.5 py-0.5 text-[9px] font-terminal text-[var(--color-text-muted)] rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface)]"
        >
          {key}
        </kbd>
      ))}
    </div>
  </div>
);
