"use client";

import React, { useEffect, useState } from "react";
import {
  Clock,
  Database,
  FileText,
  Zap,
  ArrowRight,
  Activity,
  Cpu,
  Eye,
  Layers,
  Shield,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, Project } from "@/lib/api";
import { WorkflowEngine } from "@/components/WorkflowEngine";
import { useAstraStore } from "@/stores/useAstraStore";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusDot } from "@/components/ui/StatusDot";
import { SystemLabel } from "@/components/ui/SystemLabel";

/* ══════════════════════════════════════════════════════════════════════
   DASHBOARD — Mission Control
   
   The command center overview of ASTRA OS.
   Shows system telemetry, recent workspaces, and workflow engine.
   ══════════════════════════════════════════════════════════════════════ */

interface DashboardProps {
  onSelectProject: (id: string, label?: string) => void;
}

export const Dashboard = ({ onSelectProject }: DashboardProps) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { telemetry } = useAstraStore();

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const data = await api.getProjects();
        setProjects(data);
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchProjects();
  }, []);

  const stats = [
    {
      label: "Neural Engine",
      value:
        telemetry.ollama_status === "connected" ? "Online" : "Offline",
      sub: telemetry.model_name !== "none" ? telemetry.model_name : "—",
      icon: Cpu,
      accent: "cyan" as const,
      status:
        telemetry.ollama_status === "connected"
          ? ("online" as const)
          : ("offline" as const),
    },
    {
      label: "Knowledge Assets",
      value: String(telemetry.documents_indexed),
      sub: `${telemetry.episodic_memories} Memories`,
      icon: Database,
      accent: "purple" as const,
      status: "online" as const,
    },
    {
      label: "CPU Load",
      value: `${telemetry.cpu_percent.toFixed(1)}%`,
      sub: "Processor",
      icon: Activity,
      accent: "amber" as const,
      percent: telemetry.cpu_percent,
    },
    {
      label: "Memory",
      value: `${telemetry.ram_usage_percent.toFixed(1)}%`,
      sub: "RAM Allocated",
      icon: Layers,
      accent: "teal" as const,
      percent: telemetry.ram_usage_percent,
    },
  ];

  const accentColors = {
    cyan: {
      border: "border-l-[var(--color-accent-cyan)]",
      icon: "text-[var(--color-accent-cyan)] bg-[var(--color-accent-cyan)]/10",
      bar: "bg-[var(--color-accent-cyan)]",
    },
    purple: {
      border: "border-l-[var(--color-accent-purple)]",
      icon: "text-[var(--color-accent-purple)] bg-[var(--color-accent-purple)]/10",
      bar: "bg-[var(--color-accent-purple)]",
    },
    amber: {
      border: "border-l-[var(--color-warning)]",
      icon: "text-[var(--color-warning)] bg-[var(--color-warning)]/10",
      bar: "bg-[var(--color-warning)]",
    },
    teal: {
      border: "border-l-[var(--color-accent-teal)]",
      icon: "text-[var(--color-accent-teal)] bg-[var(--color-accent-teal)]/10",
      bar: "bg-[var(--color-accent-teal)]",
    },
  };

  return (
    <div className="h-full w-full overflow-y-auto bg-transparent p-8 lg:p-10 space-y-10 scrollbar-hide">
      {/* ── Hero Header ──────────────────────────────────────── */}
      <header className="space-y-3">
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <SystemLabel size="sm" color="cyan" icon={<Zap size={12} />}>
            Command Center
          </SystemLabel>
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="text-3xl lg:text-4xl font-bold text-[var(--color-text-bright)] tracking-tight"
        >
          ASTRA{" "}
          <span className="text-[var(--color-text-muted)] font-light">
            OS
          </span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="text-[13px] text-[var(--color-text-muted)] max-w-lg"
        >
          {telemetry.ollama_status === "connected" ? (
            <>
              <span className="text-[var(--color-success)]">●</span>{" "}
              {telemetry.model_name} active ·{" "}
              {telemetry.documents_indexed} documents ·{" "}
              {telemetry.episodic_memories} memories
            </>
          ) : (
            <>
              <span className="text-[var(--color-danger)]">●</span>{" "}
              Neural engine offline — start Ollama to enable AI capabilities
            </>
          )}
        </motion.p>
      </header>

      {/* ── Telemetry Grid ───────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.06 }}
          >
            <GlassPanel
              intensity="surface"
              padding="md"
              rounded="xl"
              className={cn(
                "border-l-2 space-y-3 hover:border-white/10 transition-all duration-[var(--motion-hover)]",
                accentColors[stat.accent].border
              )}
            >
              <div className="flex items-center justify-between">
                <div
                  className={cn(
                    "w-9 h-9 rounded-lg flex items-center justify-center",
                    accentColors[stat.accent].icon
                  )}
                >
                  <stat.icon size={18} />
                </div>
                {stat.status && (
                  <StatusDot status={stat.status} size="sm" />
                )}
              </div>
              <div>
                <p className="text-xl font-bold text-[var(--color-text-bright)]">
                  {stat.value}
                </p>
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-text-muted)] mt-0.5">
                  {stat.label}
                </p>
                <p className="text-[10px] text-[var(--color-text-muted)] font-terminal mt-0.5">
                  {stat.sub}
                </p>
              </div>
              {stat.percent !== undefined && (
                <div className="h-1 w-full bg-[var(--color-surface)] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{
                      width: `${Math.min(stat.percent, 100)}%`,
                    }}
                    transition={{ duration: 1.2, ease: "easeOut" }}
                    className={cn(
                      "h-full rounded-full",
                      accentColors[stat.accent].bar
                    )}
                  />
                </div>
              )}
            </GlassPanel>
          </motion.div>
        ))}
      </div>

      {/* ── Main Content Grid ────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Workflows + Recent Projects */}
        <section className="lg:col-span-2 space-y-10">
          {/* Workflow Engine */}
          <WorkflowEngine />

          {/* Recent Workspaces */}
          <div className="space-y-4">
            <SystemLabel
              size="sm"
              icon={<Clock size={12} />}
              className="pt-4 border-t border-[var(--color-border-subtle)]"
            >
              Recent Workspaces
            </SystemLabel>

            <div className="space-y-2">
              {isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((n) => (
                    <div key={n} className="h-16 glass-surface rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : (
                projects.slice(0, 5).map((proj, i) => (
                  <motion.div
                    key={proj.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + i * 0.05 }}
                  >
                    <GlassPanel
                      intensity="surface"
                      padding="sm"
                      rounded="lg"
                      hover
                      onClick={() => onSelectProject(proj.id, proj.name)}
                      className="flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "w-9 h-9 rounded-lg flex items-center justify-center font-bold text-sm",
                            proj.project_type === "research"
                              ? "bg-[var(--color-accent-purple)]/10 text-[var(--color-accent-purple)] border border-[var(--color-accent-purple)]/20"
                              : proj.project_type === "code"
                              ? "bg-[var(--color-accent-cyan)]/10 text-[var(--color-accent-cyan)] border border-[var(--color-accent-cyan)]/20"
                              : "bg-[var(--color-success)]/10 text-[var(--color-success)] border border-[var(--color-success)]/20"
                          )}
                        >
                          {proj.name[0]?.toUpperCase() || "?"}
                        </div>
                        <div>
                          <p className="text-[13px] font-semibold text-[var(--color-text-bright)] group-hover:text-[var(--color-accent-cyan)] transition-colors">
                            {proj.name}
                          </p>
                          <p className="text-[10px] text-[var(--color-text-muted)] font-terminal">
                            {proj.project_type} ·{" "}
                            {new Date(
                              proj.last_accessed_at
                            ).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <ArrowRight
                        size={14}
                        className="text-[var(--color-text-muted)] group-hover:text-[var(--color-accent-cyan)] group-hover:translate-x-0.5 transition-all"
                      />
                    </GlassPanel>
                  </motion.div>
                ))
              )}

              {!isLoading && projects.length === 0 && (
                <GlassPanel
                  intensity="surface"
                  padding="lg"
                  rounded="xl"
                  className="text-center space-y-3 border-dashed"
                >
                  <p className="text-[13px] text-[var(--color-text-muted)]">
                    No workspaces yet.
                  </p>
                  <button
                    onClick={() => onSelectProject("default", "Default")}
                    className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-accent-cyan)] hover:text-[var(--color-text-bright)] transition-colors"
                  >
                    + Create Workspace
                  </button>
                </GlassPanel>
              )}
            </div>
          </div>
        </section>

        {/* Right: System Topology */}
        <section className="space-y-4">
          <SystemLabel size="sm" icon={<Eye size={12} />}>
            System Topology
          </SystemLabel>
          <GlassPanel
            intensity="surface"
            padding="lg"
            rounded="xl"
            className="space-y-6"
          >
            {/* Node Map (CSS-based, Phase 1) */}
            <div className="space-y-4">
              <TopologyNode
                label="Ollama"
                status={
                  telemetry.ollama_status === "connected"
                    ? "online"
                    : "offline"
                }
                description={
                  telemetry.model_name !== "none"
                    ? telemetry.model_name
                    : "Not loaded"
                }
              />
              <div className="w-px h-4 mx-auto" style={{ backgroundImage: 'linear-gradient(to bottom, var(--color-border-subtle) 50%, transparent 50%)', backgroundSize: '1px 4px', animation: 'flow-down 0.8s linear infinite' }} />
              <TopologyNode
                label="Agent"
                status="online"
                description="OODA Loop"
              />
              <div className="w-px h-4 mx-auto" style={{ backgroundImage: 'linear-gradient(to bottom, var(--color-border-subtle) 50%, transparent 50%)', backgroundSize: '1px 4px', animation: 'flow-down 0.8s linear infinite' }} />
              <div className="grid grid-cols-2 gap-3">
                <TopologyNode
                  label="Memory"
                  status="online"
                  description={`${telemetry.episodic_memories} eps`}
                  compact
                />
                <TopologyNode
                  label="Documents"
                  status="online"
                  description={`${telemetry.documents_indexed} files`}
                  compact
                />
              </div>
            </div>

            {/* Metrics */}
            <div className="space-y-3 pt-4 border-t border-[var(--color-border-subtle)]">
              <MetricBar label="Documents" percent={telemetry.documents_indexed > 0 ? Math.min(telemetry.documents_indexed * 10, 100) : 0} color="emerald" />
              <MetricBar
                label="CPU"
                percent={telemetry.cpu_percent}
                color="cyan"
              />
              <MetricBar
                label="RAM"
                percent={telemetry.ram_usage_percent}
                color="purple"
              />
            </div>
          </GlassPanel>
        </section>
      </div>
    </div>
  );
};

// ── Sub-components ──────────────────────────────────────────────────

const TopologyNode = ({
  label,
  status,
  description,
  compact,
}: {
  label: string;
  status: "online" | "offline";
  description: string;
  compact?: boolean;
}) => (
  <div
    className={cn(
      "glass-surface rounded-xl flex items-center gap-3",
      compact ? "p-2.5" : "p-3"
    )}
  >
    <StatusDot status={status} size="sm" />
    <div className="min-w-0">
      <p
        className={cn(
          "font-semibold text-[var(--color-text-bright)]",
          compact ? "text-[11px]" : "text-[12px]"
        )}
      >
        {label}
      </p>
      <p className="text-[9px] text-[var(--color-text-muted)] font-terminal truncate">
        {description}
      </p>
    </div>
  </div>
);

const MetricBar = ({
  label,
  percent,
  color,
}: {
  label: string;
  percent: number;
  color: "cyan" | "purple" | "emerald";
}) => {
  const barColors = {
    cyan: "bg-[var(--color-accent-cyan)]",
    purple: "bg-[var(--color-accent-purple)]",
    emerald: "bg-[var(--color-success)]",
  };
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider font-bold">
          {label}
        </span>
        <span className="text-[10px] text-[var(--color-text-body)] font-terminal font-semibold">
          {percent.toFixed(1)}%
        </span>
      </div>
      <div className="h-1 w-full bg-[var(--color-surface)] rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(percent, 100)}%` }}
          transition={{ duration: 1.2, ease: "easeOut" }}
          className={cn("h-full rounded-full", barColors[color])}
        />
      </div>
    </div>
  );
};
