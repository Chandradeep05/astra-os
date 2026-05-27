"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Cpu,
  Terminal,
  ShieldAlert,
  Paperclip,
  Loader2,
  Square,
  Eye,
  Wrench,
  Brain,
  Zap,
  MessageSquare,
  AlertTriangle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { authFetch, API_BASE_URL } from "@/lib/api";
import { useAstraStore } from "@/stores/useAstraStore";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusDot } from "@/components/ui/StatusDot";
import { SystemLabel } from "@/components/ui/SystemLabel";

/* ══════════════════════════════════════════════════════════════════════
   ASTRA AGENT — Autonomous Execution Cockpit
   
   Preserves ALL SSE streaming logic, OODA phase tracking,
   approval gate, and abort controller from the certified version.
   Only the visual presentation changes.
   ══════════════════════════════════════════════════════════════════════ */

type AnimationState = "idle" | "thinking" | "typing" | "speaking" | "waking";

interface AgentStreamEvent {
  type: "thought" | "tool_call" | "tool_result" | "answer" | "phase_change" | "approval_required" | "done" | "error";
  phase: "observe" | "think" | "act" | "reflect" | null;
  content: string | null;
  data: any | null;
}

const OODA_PHASES = ["observe", "think", "act", "reflect"] as const;

export const AstraAgent = () => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: "Neural agent initialized. Awaiting autonomous task assignment..." }
  ]);
  const [input, setInput] = useState("");
  const [avatarState, setAvatarState] = useState<AnimationState>("idle");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showApproval, setShowApproval] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [thinkingText, setThinkingText] = useState<string | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [toolHistory, setToolHistory] = useState<{ tool: string; status: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const { setEnvironmentState } = useAstraStore();

  // Auto-scroll
  useEffect(() => {
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Sync environment state with agent state
  useEffect(() => {
    if (isStreaming) {
      setEnvironmentState(avatarState === "waking" ? "thinking" : "executing");
    } else if (showApproval) {
      setEnvironmentState("warning");
    } else {
      setEnvironmentState("idle");
    }
  }, [isStreaming, avatarState, showApproval, setEnvironmentState]);

  // ── Preserved Logic (unchanged from certified version) ────────

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", "default");
    try {
      setMessages((prev) => [...prev, { role: "system", content: `Uploading document: ${file.name}...` }]);
      const response = await authFetch(`${API_BASE_URL}/documents/upload`, { method: "POST", body: formData });
      if (!response.ok) throw new Error("Upload failed");
      const data = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", content: `✅ ${data.filename.toUpperCase()} INGESTED: ASTRA has processed this file into memory.` }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "system", content: `⚠️ Document ingestion failed: ${String(error)}` }]);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleApproveDecision = async (approved: boolean) => {
    if (!showApproval?.task_id) return;
    try {
      const res = await authFetch(`${API_BASE_URL}/agent/approve/${showApproval.task_id}?approved=${approved}`, { method: "POST" });
      if (!res.ok) throw new Error("Approval failed");
      setShowApproval(null);
      setMessages((prev) => [...prev, { role: "system", content: approved ? "✅ Action approved by user." : "❌ Action rejected by user." }]);
    } catch (error) {
      console.error("Approval error:", error);
    }
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setAvatarState("idle");
    setThinkingText(null);
    setMessages((prev) => [...prev, { role: "system", content: "⏹️ Generation stopped by user." }]);
  };

  const handleAgentEvent = (event: AgentStreamEvent) => {
    // Track OODA phase
    if (event.phase) setCurrentPhase(event.phase);

    switch (event.type) {
      case "thought":
        setAvatarState("thinking");
        if (event.content) {
          setThinkingText(event.content);
          const contentLower = event.content.toLowerCase();
          if (contentLower.includes("wak") || contentLower.includes("loading model") || contentLower.includes("initializ")) {
            setAvatarState("waking");
          }
        }
        break;
      case "tool_call":
        setAvatarState("typing");
        if (event.data?.tool) {
          setThinkingText(`Executing: ${event.data.tool}`);
          setToolHistory((prev) => [...prev.slice(-4), { tool: event.data.tool, status: "running" }]);
        }
        break;
      case "tool_result":
        setToolHistory((prev) => {
          const updated = [...prev];
          if (updated.length > 0) updated[updated.length - 1].status = "done";
          return updated;
        });
        break;
      case "answer":
        setAvatarState("speaking");
        setThinkingText(null);
        if (event.content) {
          setMessages((prev) => {
            const newMsgs = [...prev];
            const lastMsg = newMsgs[newMsgs.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              newMsgs[newMsgs.length - 1] = { ...lastMsg, content: lastMsg.content + event.content! };
            } else {
              newMsgs.push({ role: "assistant", content: event.content! });
            }
            return newMsgs;
          });
        }
        break;
      case "approval_required":
        setAvatarState("idle");
        setShowApproval({ tool: event.data?.tool, arguments: event.data?.arguments, task_id: event.data?.task_id });
        break;
      case "done":
      case "error":
        setAvatarState("idle");
        setThinkingText(null);
        if (event.type === "error" && event.content) {
          setMessages((prev) => [...prev, { role: "system", content: `Error: ${event.content}` }]);
        }
        break;
    }
  };

  const runAgentTask = async (task: string) => {
    if (!task.trim() || isStreaming) return;
    setMessages((prev) => [...prev, { role: "user", content: task }]);
    setInput("");
    setAvatarState("thinking");
    setIsStreaming(true);
    setShowApproval(null);
    setThinkingText(null);
    setToolHistory([]);
    setCurrentPhase(null);
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      const response = await authFetch(`${API_BASE_URL}/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
        signal: controller.signal,
      });
      if (!response.body) throw new Error("No readable stream available");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.substring(6).trim();
          if (dataStr === "[DONE]") {
            setAvatarState("idle");
            setIsStreaming(false);
            setThinkingText(null);
            abortControllerRef.current = null;
            return;
          }
          try {
            const event: AgentStreamEvent = JSON.parse(dataStr);
            handleAgentEvent(event);
          } catch (e) {
            console.error("Failed to parse SSE event:", e);
          }
        }
      }
    } catch (error: any) {
      if (error?.name === "AbortError") return;
      console.error("Stream failure:", error);
      setMessages((prev) => [...prev, { role: "system", content: `Error: ${String(error)}` }]);
    } finally {
      setAvatarState("idle");
      setIsStreaming(false);
      setThinkingText(null);
      abortControllerRef.current = null;
    }
  };

  useEffect(() => {
    return () => { if (abortControllerRef.current) abortControllerRef.current.abort(); };
  }, []);

  // ── Derived visual state ──────────────────────────────────────

  const statusDotState = avatarState === "idle" ? "online"
    : avatarState === "thinking" ? "thinking"
    : avatarState === "waking" ? "thinking"
    : avatarState === "typing" ? "executing"
    : "executing";

  return (
    <div className="flex flex-col h-full w-full bg-transparent relative overflow-hidden">
      {/* ── Header ───────────────────────────────────────────── */}
      <header className="h-14 shrink-0 border-b border-[var(--color-border-subtle)] flex items-center justify-between px-6 bg-[var(--color-void)]/60 backdrop-blur-xl z-30">
        <div className="flex items-center gap-3">
          <StatusDot status={statusDotState} size="md" />
          <div>
            <h1 className="text-[14px] font-bold text-[var(--color-text-bright)]">
              Neural Agent
            </h1>
          </div>
        </div>

        {/* OODA Phase Bar */}
        <div className="hidden md:flex items-center gap-1">
          {OODA_PHASES.map((phase) => (
            <div
              key={phase}
              className={cn(
                "px-2.5 py-1 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all duration-300",
                currentPhase === phase
                  ? "bg-[var(--color-accent-cyan)]/15 text-[var(--color-accent-cyan)] border border-[var(--color-accent-cyan)]/30"
                  : "text-[var(--color-text-muted)] bg-[var(--color-surface)]/50"
              )}
            >
              {phase}
            </div>
          ))}
        </div>

        {/* Stop Button */}
        {isStreaming && (
          <button
            onClick={handleStopGeneration}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--color-danger)]/15 border border-[var(--color-danger)]/30 text-[var(--color-danger)] text-[10px] font-bold uppercase tracking-wider hover:bg-[var(--color-danger)]/25 transition-colors"
          >
            <Square size={10} className="fill-current" />
            Stop
          </button>
        )}
      </header>

      {/* ── Main Layout ──────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Chat Log */}
        <div className="flex-1 min-h-0 flex flex-col">
          <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-6 space-y-3 scrollbar-hide">
            <AnimatePresence initial={false}>
              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    "p-4 rounded-xl max-w-[85%] text-[13px] leading-relaxed",
                    m.role === "user"
                      ? "bg-[var(--color-accent-cyan)]/10 border border-[var(--color-accent-cyan)]/20 text-[var(--color-text-bright)] ml-auto"
                      : m.role === "system"
                      ? "bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/20 text-[var(--color-warning)]"
                      : "glass-surface text-[var(--color-text-body)] mr-auto"
                  )}
                >
                  <p className="whitespace-pre-wrap break-words overflow-hidden">
                    {m.content}
                  </p>
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Idle State — shown when only the init message exists and not streaming */}
            {messages.length <= 1 && !isStreaming && (
              <div className="flex flex-col items-center justify-center pt-16 pb-8 space-y-8">
                <div className="text-center space-y-2">
                  <p className="font-terminal text-[13px] text-[var(--color-text-muted)] tracking-wide">
                    Awaiting task assignment
                    <span
                      className="inline-block w-[2px] h-[14px] bg-[var(--color-accent-cyan)] ml-1 align-middle"
                      style={{ animation: "blink-cursor 1.2s ease-in-out infinite" }}
                    />
                  </p>
                  <p className="text-[11px] text-[var(--color-text-muted)]/60">
                    Assign a task below, or try an example
                  </p>
                </div>
                <div className="flex flex-wrap justify-center gap-2 max-w-md">
                  {[
                    "Analyze uploaded documents for key themes",
                    "Summarize my knowledge base",
                    "Search the web for latest AI papers",
                    "Run a scheduled integrity check",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => runAgentTask(prompt)}
                      className="px-3 py-2 rounded-lg glass-surface text-[11px] text-[var(--color-text-body)] hover:text-[var(--color-accent-cyan)] hover:border-[var(--color-accent-cyan)]/30 transition-all duration-150 text-left"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Typing indicator — visible when streaming but no answer text yet */}
            {isStreaming && messages[messages.length - 1]?.role === "user" && (
              <div className="flex items-center gap-1.5 p-4 mr-auto">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-cyan)] animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-cyan)] animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent-cyan)] animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            )}
          </div>

          {/* Approval Gate */}
          <AnimatePresence>
            {showApproval && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="mx-6 mb-3"
              >
                <GlassPanel
                  intensity="elevated"
                  padding="md"
                  rounded="xl"
                  className="border-l-2 border-l-[var(--color-warning)] space-y-3"
                >
                  <div className="flex items-center gap-2">
                    <ShieldAlert size={14} className="text-[var(--color-warning)]" />
                    <SystemLabel size="xs" color="amber">
                      Approval Required
                    </SystemLabel>
                  </div>
                  <p className="text-[12px] text-[var(--color-text-body)]">
                    Agent requests permission to execute <strong className="text-[var(--color-text-bright)]">{showApproval.tool}</strong>
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleApproveDecision(true)}
                      className="flex-1 px-4 py-2 rounded-lg bg-[var(--color-success)]/15 border border-[var(--color-success)]/30 text-[var(--color-success)] text-[10px] font-bold uppercase tracking-wider hover:bg-[var(--color-success)]/25 transition-all active:scale-[0.98]"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleApproveDecision(false)}
                      className="px-4 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border-subtle)] text-[var(--color-text-muted)] text-[10px] font-bold uppercase tracking-wider hover:bg-[var(--color-surface-elevated)] transition-all"
                    >
                      Reject
                    </button>
                  </div>
                </GlassPanel>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Input */}
          <div className="p-4 border-t border-[var(--color-border-subtle)] bg-[var(--color-void)]/60">
            <div className="flex items-center gap-2">
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                onChange={handleFileUpload}
                accept=".pdf,.docx,.xlsx,.txt,.md,.json,.png,.jpg,.jpeg,.wav,.mp3"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isStreaming}
                className="p-2.5 rounded-lg glass-surface text-[var(--color-text-muted)] hover:text-[var(--color-text-body)] transition-colors shrink-0 disabled:opacity-40"
                title="Upload Document"
              >
                {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
              </button>
              <input
                className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border-subtle)] rounded-xl px-4 py-2.5 text-[13px] text-[var(--color-text-bright)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent-cyan)]/40 transition-colors disabled:opacity-40"
                placeholder="Assign autonomous task..."
                value={input}
                disabled={isStreaming}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !isStreaming && runAgentTask(input)}
              />
              <button
                onClick={() => runAgentTask(input)}
                disabled={!input.trim() || isStreaming}
                className="p-2.5 rounded-lg bg-[var(--color-accent-cyan)]/15 border border-[var(--color-accent-cyan)]/30 text-[var(--color-accent-cyan)] hover:bg-[var(--color-accent-cyan)]/25 transition-colors shrink-0 disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>

        {/* Right: Agent Telemetry Panel */}
        <div className="w-72 shrink-0 border-l border-[var(--color-border-subtle)] bg-[var(--color-void)]/50 p-4 space-y-4 overflow-y-auto scrollbar-hide hidden lg:flex flex-col">
          {/* Agent State */}
          <div className="space-y-3">
            <SystemLabel size="xs" color="cyan" icon={<Cpu size={10} />}>
              Agent State
            </SystemLabel>
            <GlassPanel intensity="surface" padding="md" rounded="lg" className="flex items-center gap-3">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-500",
                avatarState === "idle" ? "bg-[var(--color-success)]/10 text-[var(--color-success)]" :
                avatarState === "thinking" ? "bg-[var(--color-accent-purple)]/10 text-[var(--color-accent-purple)]" :
                avatarState === "waking" ? "bg-[var(--color-warning)]/10 text-[var(--color-warning)]" :
                "bg-[var(--color-accent-cyan)]/10 text-[var(--color-accent-cyan)]"
              )}>
                <Cpu size={20} className={cn(avatarState !== "idle" && "animate-pulse")} />
              </div>
              <div>
                <p className="text-[12px] font-semibold text-[var(--color-text-bright)] uppercase">
                  {avatarState}
                </p>
                <p className="text-[10px] text-[var(--color-text-muted)] font-terminal">
                  {isStreaming ? "SSE Active" : "Awaiting"}
                </p>
              </div>
            </GlassPanel>
          </div>

          {/* Thought Stream */}
          <div className="space-y-2 flex-1 min-h-0">
            <SystemLabel size="xs" icon={<Brain size={10} />}>
              Thought Stream
            </SystemLabel>
            <div className="space-y-1.5 overflow-y-auto max-h-48 scrollbar-hide">
              <AnimatePresence>
                {thinkingText && (
                  <motion.div
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-2.5 rounded-lg bg-[var(--color-void)] border-l-2 border-l-[var(--color-accent-cyan)] font-terminal text-[11px] text-[var(--color-accent-cyan)]"
                  >
                    {thinkingText}
                  </motion.div>
                )}
              </AnimatePresence>
              {isStreaming && !thinkingText && (
                <div className="p-2.5 rounded-lg bg-[var(--color-void)] text-[11px] font-terminal text-[var(--color-text-muted)] animate-pulse">
                  Listening for events...
                </div>
              )}
              {!isStreaming && !thinkingText && (
                <p className="text-[10px] text-[var(--color-text-muted)] font-terminal px-1">
                  No active thought processes
                </p>
              )}
            </div>
          </div>

          {/* Tool History — always visible with empty state */}
          <div className="space-y-2">
            <SystemLabel size="xs" icon={<Wrench size={10} />}>
              Tools Used
            </SystemLabel>
            {toolHistory.length > 0 ? (
              <div className="space-y-1">
                {toolHistory.map((t, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-[var(--color-surface)]/50 text-[10px]">
                    <span className="font-terminal text-[var(--color-text-body)] truncate">{t.tool}</span>
                    <StatusDot status={t.status === "running" ? "executing" : "online"} size="sm" />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-[var(--color-text-muted)] font-terminal px-1">
                No tools executed this session
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
