"use client";

import React, { useEffect, useState } from "react";
import {
  Plus,
  Zap,
  MessageSquare,
  Settings,
  Database,
  Loader2,
  X,
  Cpu,
  FileText,
  Activity,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Moon,
  Sun,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { api, Project } from "@/lib/api";
import { useAstraStore } from "@/stores/useAstraStore";
import { StatusDot } from "@/components/ui/StatusDot";
import { SystemLabel } from "@/components/ui/SystemLabel";

/* ══════════════════════════════════════════════════════════════════════
   SIDEBAR — Premium left rail navigation.
   
   Collapsed: 72px (icon-only)
   Expanded: 260px (hover or pin)
   
   Includes runtime presence footer.
   ══════════════════════════════════════════════════════════════════════ */

interface SidebarProps {
  activeProject: string;
  onSelectProject: (id: string, label?: string) => void;
}

const NAV_SECTIONS = [
  {
    title: "Core",
    items: [
      { icon: Zap, label: "Command Center", id: "dashboard" },
      { icon: Cpu, label: "Neural Agent", id: "agent" },
      { icon: MessageSquare, label: "Chat Interface", id: "default" },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { icon: Database, label: "Memory Cortex", id: "memory-browser" },
      { icon: FileText, label: "Knowledge Base", id: "documents" },
      { icon: Activity, label: "Telemetry", id: "tasks" },
    ],
  },
  {
    title: "Operations",
    items: [
      { icon: Calendar, label: "Scheduler", id: "scheduled-tasks" },
      { icon: Settings, label: "Configuration", id: "settings" },
    ],
  },
];

export const Sidebar = ({ activeProject, onSelectProject }: SidebarProps) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const {
    sidebarCollapsed,
    toggleSidebar,
    taskRunsUnreadCount,
    markTasksViewed,
    sleepStatus,
    telemetry,
    environmentState,
  } = useAstraStore();

  const [hovered, setHovered] = useState(false);
  const expanded = !sidebarCollapsed || hovered;

  const fetchProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
    } catch (error) {
      console.error("Failed to load projects", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreating(true);
    try {
      const newProj = await api.createProject({ name: newProjectName });
      setProjects([newProj, ...projects]);
      onSelectProject(newProj.id, newProj.name);
      setNewProjectName("");
      setIsModalOpen(false);
    } catch (error) {
      console.error("Failed to create project", error);
    } finally {
      setIsCreating(false);
    }
  };

  // Derive status
  const systemStatus = sleepStatus.sleeping
    ? "sleeping"
    : environmentState === "executing"
    ? "executing"
    : environmentState === "thinking"
    ? "thinking"
    : telemetry.ollama_status === "connected"
    ? "online"
    : "offline";

  return (
    <>
      <aside
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={cn(
          "h-full flex flex-col z-40 shrink-0 border-r border-[var(--color-border-subtle)] bg-[var(--color-void)]/90 backdrop-blur-xl transition-all ease-in-out",
          expanded ? "w-[260px]" : "w-[72px]",
          "duration-[var(--motion-panel)]"
        )}
      >
        {/* ── Header ────────────────────────────────────────────── */}
        <div className="h-16 flex items-center px-4 gap-3 shrink-0">
          <div className="w-9 h-9 rounded-xl bg-[var(--color-accent-cyan)]/10 border border-[var(--color-accent-cyan)]/20 flex items-center justify-center shrink-0">
            <span className="text-sm font-black text-[var(--color-accent-cyan)]">A</span>
          </div>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col min-w-0"
            >
              <span className="text-[13px] font-bold text-[var(--color-text-bright)] tracking-tight uppercase">
                ASTRA OS
              </span>
              <span className="text-[9px] font-terminal text-[var(--color-text-muted)] tracking-wider">
                v0.5.1
              </span>
            </motion.div>
          )}
        </div>

        {/* ── New Context Button ─────────────────────────────────── */}
        <div className="px-3 mb-4">
          <button
            onClick={() => setIsModalOpen(true)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-xl transition-all duration-[var(--motion-hover)] active:scale-95",
              expanded
                ? "w-full py-2.5 bg-[var(--color-accent-cyan)]/10 border border-[var(--color-accent-cyan)]/20 text-[var(--color-accent-cyan)] hover:bg-[var(--color-accent-cyan)]/15"
                : "w-11 h-11 mx-auto bg-[var(--color-surface)] border border-[var(--color-border-subtle)] text-[var(--color-text-muted)] hover:text-[var(--color-accent-cyan)] hover:border-[var(--color-accent-cyan)]/30"
            )}
          >
            <Plus size={16} />
            {expanded && (
              <span className="text-[11px] font-bold uppercase tracking-wider">
                New Context
              </span>
            )}
          </button>
        </div>

        {/* ── Navigation ─────────────────────────────────────────── */}
        <nav className="flex-1 px-2 space-y-5 overflow-y-auto scrollbar-hide">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title}>
              {expanded && (
                <div className="px-3 mb-1.5">
                  <SystemLabel size="xs">{section.title}</SystemLabel>
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const isActive = activeProject === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        onSelectProject(item.id, item.label);
                        if (item.id === "tasks") markTasksViewed();
                      }}
                      className={cn(
                        "w-full flex items-center gap-3 py-2.5 rounded-xl transition-all duration-[var(--motion-hover)] group relative",
                        expanded ? "px-3" : "px-0 justify-center",
                        isActive
                          ? "bg-[var(--color-surface-elevated)] text-[var(--color-text-bright)]"
                          : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-body)]"
                      )}
                      title={!expanded ? item.label : undefined}
                    >
                      {/* Active indicator */}
                      {isActive && (
                        <motion.div
                          layoutId="sidebar-active"
                          className="absolute left-0 w-[3px] h-5 rounded-r-full bg-[var(--color-accent-cyan)]"
                          transition={{ type: "spring", stiffness: 400, damping: 30 }}
                        />
                      )}
                      <item.icon
                        size={18}
                        className={cn(
                          "shrink-0 transition-colors",
                          isActive
                            ? "text-[var(--color-accent-cyan)]"
                            : "group-hover:text-[var(--color-text-body)]"
                        )}
                      />
                      {expanded && (
                        <span className="text-[13px] font-semibold truncate">
                          {item.label}
                        </span>
                      )}
                      {/* Unread badge for Telemetry */}
                      {item.id === "tasks" && taskRunsUnreadCount > 0 && (
                        <span
                          className={cn(
                            "shrink-0 min-w-[18px] h-[18px] px-1 rounded-full bg-[var(--color-accent-cyan)]/15 border border-[var(--color-accent-cyan)]/30 text-[9px] font-bold text-[var(--color-accent-cyan)] flex items-center justify-center",
                            expanded ? "ml-auto" : "absolute -top-1 -right-1"
                          )}
                        >
                          {taskRunsUnreadCount > 99
                            ? "99+"
                            : taskRunsUnreadCount}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {/* ── Workspaces ──────────────────────────────────────── */}
          {expanded && (
            <div>
              <div className="px-3 mb-1.5">
                <SystemLabel size="xs">Workspaces</SystemLabel>
              </div>
              <div className="space-y-0.5">
                {isLoading ? (
                  <div className="flex justify-center p-4">
                    <Loader2
                      size={14}
                      className="animate-spin text-[var(--color-text-muted)]"
                    />
                  </div>
                ) : (
                  projects.map((proj) => {
                    const isActive = activeProject === proj.id;
                    return (
                      <button
                        key={proj.id}
                        onClick={() => onSelectProject(proj.id, proj.name)}
                        className={cn(
                          "w-full flex items-center gap-3 px-3 py-2 rounded-xl transition-all duration-[var(--motion-hover)] group relative",
                          isActive
                            ? "bg-[var(--color-surface-elevated)] text-[var(--color-text-bright)]"
                            : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-body)]"
                        )}
                      >
                        {isActive && (
                          <motion.div
                            layoutId="sidebar-active"
                            className="absolute left-0 w-[3px] h-5 rounded-r-full bg-[var(--color-accent-cyan)]"
                            transition={{
                              type: "spring",
                              stiffness: 400,
                              damping: 30,
                            }}
                          />
                        )}
                        <div
                          className={cn(
                            "w-2 h-2 rounded-full shrink-0",
                            proj.project_type === "research"
                              ? "bg-[var(--color-accent-purple)]"
                              : proj.project_type === "code"
                              ? "bg-[var(--color-accent-cyan)]"
                              : "bg-[var(--color-success)]"
                          )}
                        />
                        <span className="text-[12px] font-medium truncate">
                          {proj.name}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </nav>

        {/* ── Runtime Presence Footer ─────────────────────────── */}
        <div className="border-t border-[var(--color-border-subtle)] p-3 space-y-2 bg-[var(--color-void)]/50">
          {/* Sleep toggle */}
          {expanded && sleepStatus.sleeping && (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-[var(--color-accent-purple)]/5 border border-[var(--color-accent-purple)]/10">
              <Moon size={12} className="text-[var(--color-accent-purple)]" />
              <span className="text-[10px] font-terminal text-[var(--color-accent-purple)] uppercase tracking-wider">
                Sleep Mode
              </span>
            </div>
          )}

          {/* Status bar */}
          <div
            className={cn(
              "flex items-center gap-2",
              expanded ? "px-2" : "justify-center"
            )}
          >
            <StatusDot status={systemStatus} size="sm" />
            {expanded && (
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-terminal text-[var(--color-text-muted)] truncate uppercase tracking-wider">
                  {telemetry.model_name !== "none"
                    ? telemetry.model_name
                    : "No Model"}
                </p>
              </div>
            )}
          </div>

          {/* Founder badge */}
          <div
            className={cn(
              "flex items-center gap-2 rounded-xl bg-[var(--color-surface)]/60 border border-[var(--color-border-subtle)] transition-all",
              expanded ? "px-3 py-2" : "p-2 justify-center"
            )}
          >
            <div className="w-6 h-6 rounded-full bg-[var(--color-success)]/15 border border-[var(--color-success)]/25 flex items-center justify-center text-[9px] text-[var(--color-success)] font-bold shrink-0">
              F
            </div>
            {expanded && (
              <span className="text-[10px] font-bold text-[var(--color-text-body)] uppercase tracking-wider">
                Founder Mode
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* ── New Project Modal ──────────────────────────────────── */}
      <AnimatePresence>
        {isModalOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsModalOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="relative w-full max-w-md glass-elevated rounded-2xl p-8 shadow-2xl overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-[var(--color-accent-cyan)] to-[var(--color-accent-purple)]" />
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-bold text-[var(--color-text-bright)]">
                  Initialize Context
                </h3>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-2 hover:bg-white/5 rounded-xl text-[var(--color-text-muted)] hover:text-[var(--color-text-body)] transition-colors"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleCreateProject} className="space-y-6">
                <div>
                  <SystemLabel className="mb-2 block" size="xs">
                    Workspace Name
                  </SystemLabel>
                  <input
                    autoFocus
                    type="text"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    placeholder="e.g., Research Alpha"
                    className="w-full bg-[var(--color-surface)] border border-[var(--color-border-subtle)] rounded-xl px-4 py-3 text-[var(--color-text-bright)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent-cyan)]/40 transition-colors font-medium text-[14px]"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isCreating || !newProjectName.trim()}
                  className="w-full py-3.5 rounded-xl bg-[var(--color-accent-cyan)]/10 border border-[var(--color-accent-cyan)]/20 text-[var(--color-accent-cyan)] font-bold text-[12px] uppercase tracking-wider flex items-center justify-center gap-2 hover:bg-[var(--color-accent-cyan)]/15 transition-all disabled:opacity-40"
                >
                  {isCreating ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    "Initialize Context"
                  )}
                </button>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};
