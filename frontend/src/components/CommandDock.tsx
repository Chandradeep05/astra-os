"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Search,
  Command,
  MessageSquare,
  Upload,
  Cpu,
  Database,
  Settings,
  Calendar,
  Activity,
  FileText,
  ArrowRight,
  CornerDownLeft,
  Moon,
  Zap,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAstraStore } from "@/stores/useAstraStore";
import { StatusDot } from "@/components/ui/StatusDot";

/* ══════════════════════════════════════════════════════════════════════
   COMMAND DOCK — The soul of ASTRA OS.
   
   Bottom bar + Cmd+K command palette.
   Fast, keyboard-first, premium.
   ══════════════════════════════════════════════════════════════════════ */

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: React.ReactNode;
  section: string;
  action: () => void;
  keywords?: string[];
}

export const CommandDock = () => {
  const {
    commandPaletteOpen,
    openCommandPalette,
    closeCommandPalette,
    toggleCommandPalette,
    setActiveView,
    taskRunsUnreadCount,
    environmentState,
    sleepStatus,
    telemetry,
  } = useAstraStore();

  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // ── Command registry ──────────────────────────────────────────

  const commands: CommandItem[] = useMemo(
    () => [
      // Navigation
      {
        id: "nav-dashboard",
        label: "Command Center",
        description: "System overview and telemetry",
        icon: <Zap size={16} />,
        section: "Navigation",
        action: () => setActiveView("dashboard", "Dashboard"),
        keywords: ["home", "dashboard", "overview"],
      },
      {
        id: "nav-agent",
        label: "Neural Agent",
        description: "Autonomous AI execution",
        icon: <Cpu size={16} />,
        section: "Navigation",
        action: () => setActiveView("agent", "Agent"),
        keywords: ["agent", "autonomous", "ai", "run"],
      },
      {
        id: "nav-memory",
        label: "Memory Cortex",
        description: "Episodic memory browser",
        icon: <Database size={16} />,
        section: "Navigation",
        action: () => setActiveView("memory-browser", "Memory"),
        keywords: ["memory", "episodes", "cortex", "brain"],
      },
      {
        id: "nav-documents",
        label: "Knowledge Base",
        description: "Document management & RAG",
        icon: <FileText size={16} />,
        section: "Navigation",
        action: () => setActiveView("documents", "Documents"),
        keywords: ["documents", "files", "upload", "rag", "knowledge"],
      },
      {
        id: "nav-tasks",
        label: "Telemetry Feed",
        description: "Background task logs",
        icon: <Activity size={16} />,
        section: "Navigation",
        action: () => setActiveView("tasks", "Tasks"),
        keywords: ["tasks", "logs", "telemetry", "background"],
      },
      {
        id: "nav-scheduler",
        label: "Scheduler Matrix",
        description: "Cron job management",
        icon: <Calendar size={16} />,
        section: "Navigation",
        action: () => setActiveView("scheduled-tasks", "Scheduler"),
        keywords: ["scheduler", "cron", "schedule", "jobs"],
      },
      {
        id: "nav-settings",
        label: "System Configuration",
        description: "Agent rules & preferences",
        icon: <Settings size={16} />,
        section: "Navigation",
        action: () => setActiveView("settings", "Settings"),
        keywords: ["settings", "config", "rules", "preferences"],
      },
      // Actions
      {
        id: "action-chat",
        label: "New Chat",
        description: "Start a new conversation",
        icon: <MessageSquare size={16} />,
        section: "Actions",
        action: () => setActiveView("default", "Primary Core"),
        keywords: ["chat", "new", "conversation", "message"],
      },
    ],
    [setActiveView]
  );

  // ── Fuzzy filter ──────────────────────────────────────────────

  const filteredCommands = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description?.toLowerCase().includes(q) ||
        cmd.keywords?.some((k) => k.includes(q))
    );
  }, [query, commands]);

  // ── Group by section ──────────────────────────────────────────

  const groupedCommands = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {};
    filteredCommands.forEach((cmd) => {
      if (!groups[cmd.section]) groups[cmd.section] = [];
      groups[cmd.section].push(cmd);
    });
    return groups;
  }, [filteredCommands]);

  // ── Keyboard navigation ───────────────────────────────────────

  const executeCommand = useCallback(
    (cmd: CommandItem) => {
      cmd.action();
      closeCommandPalette();
      setQuery("");
      setSelectedIndex(0);
    },
    [closeCommandPalette]
  );

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    if (commandPaletteOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [commandPaletteOpen]);

  // ── Global Cmd+K handler ──────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggleCommandPalette();
      }
      // ⌘/ — open palette and focus search
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        openCommandPalette();
      }
      if (e.key === "Escape" && commandPaletteOpen) {
        e.preventDefault();
        closeCommandPalette();
        setQuery("");
      }
      // ⌘1-6 — quick view navigation
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey) {
        const viewMap: Record<string, [string, string]> = {
          "1": ["dashboard", "Dashboard"],
          "2": ["agent", "Agent"],
          "3": ["default", "Primary Core"],
          "4": ["memory-browser", "Memory"],
          "5": ["documents", "Documents"],
          "6": ["settings", "Settings"],
        };
        const entry = viewMap[e.key];
        if (entry) {
          e.preventDefault();
          setActiveView(entry[0], entry[1]);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [commandPaletteOpen, toggleCommandPalette, openCommandPalette, closeCommandPalette, setActiveView]);

  // ── Keyboard navigation inside palette ────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          executeCommand(filteredCommands[selectedIndex]);
        }
      }
    },
    [filteredCommands, selectedIndex, executeCommand]
  );

  // ── Scroll selected item into view ────────────────────────────

  useEffect(() => {
    if (listRef.current) {
      const selected = listRef.current.querySelector("[data-selected=true]");
      selected?.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  // ── Derive status dot state ───────────────────────────────────

  const statusDotState = sleepStatus.sleeping
    ? "sleeping"
    : environmentState === "executing"
    ? "executing"
    : environmentState === "thinking"
    ? "thinking"
    : environmentState === "warning"
    ? "warning"
    : environmentState === "error"
    ? "error"
    : telemetry.ollama_status === "connected"
    ? "online"
    : "offline";

  return (
    <>
      {/* ── Bottom Dock Bar ──────────────────────────────────────── */}
      <div className="h-14 border-t border-[var(--color-border-subtle)] bg-[var(--color-void)]/80 backdrop-blur-xl flex items-center justify-between px-4 z-30 relative">
        {/* Left: Status */}
        <div className="flex items-center gap-3">
          <StatusDot status={statusDotState} size="sm" />
          <span className="text-[10px] font-terminal text-[var(--color-text-muted)] uppercase tracking-wider hidden md:inline">
            {sleepStatus.sleeping
              ? "SLEEPING"
              : environmentState === "executing"
              ? "EXECUTING"
              : environmentState === "thinking"
              ? "THINKING"
              : "READY"}
          </span>
        </div>

        {/* Center: Command trigger */}
        <button
          onClick={openCommandPalette}
          className="flex items-center gap-3 px-5 py-2 rounded-xl glass-surface hover:glass-panel transition-all duration-[var(--motion-hover)] group max-w-md w-full md:w-96"
        >
          <Search
            size={14}
            className="text-[var(--color-text-muted)] group-hover:text-[var(--color-accent-cyan)] transition-colors"
          />
          <span className="text-[12px] text-[var(--color-text-muted)] group-hover:text-[var(--color-text-body)] transition-colors flex-1 text-left">
            Search commands...
          </span>
          <kbd className="hidden md:flex items-center gap-0.5 text-[10px] text-[var(--color-text-muted)] font-terminal px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface)]">
            <Command size={10} />K
          </kbd>
        </button>

        {/* Right: Telemetry micro-stats */}
        <div className="flex items-center gap-4">
          {taskRunsUnreadCount > 0 && (
            <button
              onClick={() => {
                setActiveView("tasks", "Tasks");
              }}
              className="relative"
            >
              <Activity size={14} className="text-[var(--color-text-muted)]" />
              <span className="absolute -top-1 -right-1.5 w-3.5 h-3.5 bg-[var(--color-accent-cyan)] rounded-full text-[8px] font-bold text-black flex items-center justify-center">
                {taskRunsUnreadCount > 9 ? "9+" : taskRunsUnreadCount}
              </span>
            </button>
          )}
          <span className="text-[10px] font-terminal text-[var(--color-text-muted)] hidden lg:inline">
            {telemetry.model_name !== "none"
              ? telemetry.model_name
              : "NO MODEL"}
          </span>
        </div>
      </div>

      {/* ── Command Palette Overlay ──────────────────────────────── */}
      <AnimatePresence>
        {commandPaletteOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
              onClick={() => {
                closeCommandPalette();
                setQuery("");
              }}
            />

            {/* Palette */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{
                duration: 0.2,
                ease: [0.16, 1, 0.3, 1],
              }}
              className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg z-50"
            >
              <div className="glass-elevated rounded-2xl overflow-hidden shadow-2xl shadow-black/40 border border-white/10">
                {/* Search Input */}
                <div className="flex items-center gap-3 p-4 border-b border-[var(--color-border-subtle)]">
                  <Search size={18} className="text-[var(--color-text-muted)] shrink-0" />
                  <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type a command or search..."
                    className="w-full bg-transparent text-[15px] text-[var(--color-text-bright)] placeholder:text-[var(--color-text-muted)] focus:outline-none font-medium"
                  />
                  <kbd className="text-[10px] text-[var(--color-text-muted)] font-terminal px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)]">
                    ESC
                  </kbd>
                </div>

                {/* Results */}
                <div
                  ref={listRef}
                  className="max-h-[320px] overflow-y-auto p-2 scrollbar-hide"
                >
                  {Object.entries(groupedCommands).map(
                    ([section, items]) => (
                      <div key={section} className="mb-2">
                        <div className="px-3 py-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)]">
                            {section}
                          </span>
                        </div>
                        {items.map((cmd) => {
                          const globalIndex = filteredCommands.indexOf(cmd);
                          const isSelected = globalIndex === selectedIndex;
                          return (
                            <button
                              key={cmd.id}
                              data-selected={isSelected}
                              onClick={() => executeCommand(cmd)}
                              onMouseEnter={() =>
                                setSelectedIndex(globalIndex)
                              }
                              className={cn(
                                "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors duration-75",
                                isSelected
                                  ? "bg-[var(--color-surface-elevated)] text-[var(--color-text-bright)]"
                                  : "text-[var(--color-text-body)] hover:bg-[var(--color-surface)]"
                              )}
                            >
                              <span
                                className={cn(
                                  "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                                  isSelected
                                    ? "bg-[var(--color-accent-cyan)]/10 text-[var(--color-accent-cyan)]"
                                    : "bg-[var(--color-surface)] text-[var(--color-text-muted)]"
                                )}
                              >
                                {cmd.icon}
                              </span>
                              <div className="flex-1 min-w-0">
                                <span className="text-[13px] font-semibold block truncate">
                                  {cmd.label}
                                </span>
                                {cmd.description && (
                                  <span className="text-[11px] text-[var(--color-text-muted)] block truncate">
                                    {cmd.description}
                                  </span>
                                )}
                              </div>
                              {isSelected && (
                                <CornerDownLeft
                                  size={12}
                                  className="text-[var(--color-text-muted)] shrink-0"
                                />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )
                  )}
                  {filteredCommands.length === 0 && (
                    <div className="px-3 py-8 text-center">
                      <p className="text-[13px] text-[var(--color-text-muted)]">
                        No commands found for &ldquo;{query}&rdquo;
                      </p>
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between px-4 py-2.5 border-t border-[var(--color-border-subtle)] bg-[var(--color-void)]/50">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)] font-terminal">
                      <span className="px-1 py-0.5 rounded border border-[var(--color-border-subtle)] text-[9px]">↑↓</span>
                      Navigate
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)] font-terminal">
                      <span className="px-1 py-0.5 rounded border border-[var(--color-border-subtle)] text-[9px]">⏎</span>
                      Select
                    </span>
                  </div>
                  <span className="text-[9px] text-[var(--color-text-muted)] font-terminal uppercase tracking-wider">
                    ASTRA OS
                  </span>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
};
