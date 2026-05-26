"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Cpu, Terminal, ShieldAlert, Paperclip, Loader2, StopCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { authFetch, API_BASE_URL } from "@/lib/api";

type AnimationState = "idle" | "thinking" | "typing" | "speaking" | "waking";

interface AgentStreamEvent {
  type: "thought" | "tool_call" | "tool_result" | "answer" | "phase_change" | "approval_required" | "done" | "error";
  phase: "observe" | "think" | "act" | "reflect" | null;
  content: string | null;
  data: any | null;
}

export const AstraAgent = () => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: "Agent Core initialized. Awaiting autonomous task execution..." }
  ]);
  const [input, setInput] = useState("");
  const [avatarState, setAvatarState] = useState<AnimationState>("idle");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showApproval, setShowApproval] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [thinkingText, setThinkingText] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll chat to bottom when messages change — use scrollTop
  // instead of scrollIntoView to avoid scrolling ancestor containers
  useEffect(() => {
    const el = chatScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", "default");

    try {
      setMessages((prev) => [...prev, { role: "system", content: `Uploading document: ${file.name}...` }]);
      const response = await authFetch(`${API_BASE_URL}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Upload failed");
      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `✅ ${data.filename.toUpperCase()} INGESTED: ASTRA has processed this file into memory.`,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: `⚠️ Document ingestion failed: ${String(error)}`,
        },
      ]);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleApproveDecision = async (approved: boolean) => {
    if (!showApproval?.task_id) return;
    
    try {
      const res = await authFetch(`${API_BASE_URL}/agent/approve/${showApproval.task_id}?approved=${approved}`, {
        method: "POST"
      });
      if (!res.ok) throw new Error("Approval failed");
      setShowApproval(null);
      setMessages((prev) => [
        ...prev,
        { role: "system", content: approved ? "✅ Action approved by user." : "❌ Action rejected by user." }
      ]);
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
    setMessages((prev) => [
      ...prev,
      { role: "system", content: "⏹️ Generation stopped by user." }
    ]);
  };

  const runAgentTask = async (task: string) => {
    if (!task.trim() || isStreaming) return;

    setMessages((prev) => [...prev, { role: "user", content: task }]);
    setInput("");
    setAvatarState("thinking");
    setIsStreaming(true);
    setShowApproval(null);
    setThinkingText(null);

    // Create new AbortController for this stream
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
      if (error?.name === "AbortError") {
        // User cancelled — already handled in handleStopGeneration
        return;
      }
      console.error("Stream failure:", error);
      setMessages((prev) => [...prev, { role: "system", content: `Error: ${String(error)}` }]);
    } finally {
      setAvatarState("idle");
      setIsStreaming(false);
      setThinkingText(null);
      abortControllerRef.current = null;
    }
  };

  const handleAgentEvent = (event: AgentStreamEvent) => {
    switch (event.type) {
      case "thought":
        setAvatarState("thinking");
        // Display waking/thinking thoughts in the telemetry panel
        if (event.content) {
          setThinkingText(event.content);
          // Check for waking-related thoughts
          const contentLower = event.content.toLowerCase();
          if (contentLower.includes("wak") || contentLower.includes("loading model") || contentLower.includes("initializ")) {
            setAvatarState("waking");
          }
        }
        break;
      case "tool_call":
        setAvatarState("typing");
        if (event.data?.tool) {
          setThinkingText(`Executing tool: ${event.data.tool}`);
        }
        break;
      case "answer":
        setAvatarState("speaking");
        setThinkingText(null);
        if (event.content) {
          setMessages((prev) => {
            const newMsgs = [...prev];
            const lastMsg = newMsgs[newMsgs.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              newMsgs[newMsgs.length - 1] = {
                ...lastMsg,
                content: lastMsg.content + event.content!,
              };
            } else {
              newMsgs.push({
                role: "assistant",
                content: event.content!,
              });
            }
            return newMsgs;
          });
        }
        break;
      case "approval_required":
        setAvatarState("idle");
        setShowApproval({
          tool: event.data?.tool,
          arguments: event.data?.arguments,
          task_id: event.data?.task_id,
        });
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

  // Cleanup AbortController on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Maps state to a mock 3D visual fallback HUD for demonstration
  const statusColor = {
    idle: "bg-emerald-500",
    thinking: "bg-purple-500",
    typing: "bg-blue-500",
    speaking: "bg-amber-500",
    waking: "bg-orange-500",
  }[avatarState];

  return (
    <div className="flex flex-col h-full w-full bg-[#08080a] relative overflow-hidden">
      {/* Header */}
      <header className="h-20 shrink-0 border-b border-white/10 flex items-center justify-between px-8 backdrop-blur-2xl bg-black/40 z-30">
        <div className="flex items-center gap-5">
          <div className="relative">
            <div className={cn("w-3 h-3 rounded-full transition-all duration-700 relative z-10 animate-pulse", statusColor)} />
            <div className={cn("absolute inset-0 blur-md rounded-full opacity-50", statusColor)} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black text-blue-500 uppercase tracking-[0.3em]">Phase 5 Enabled</span>
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">Autonomous Agent</h1>
          </div>
        </div>
      </header>

      {/* Main Layout Area */}
      <div className="flex flex-1 min-h-0 overflow-hidden p-6 gap-6">
        
        {/* Left: Chat Log */}
        <div className="flex-1 min-h-0 flex flex-col bg-white/[0.02] border border-white/5 rounded-[2rem] overflow-hidden shadow-2xl relative">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-purple-500" />
          
          <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-6 space-y-4">
            <AnimatePresence initial={false}>
              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className={cn(
                    "p-4 rounded-2xl max-w-[85%] text-sm",
                    m.role === "user" ? "bg-blue-600 text-white ml-auto" : 
                    m.role === "system" ? "bg-red-500/20 text-red-200" : 
                    "bg-white/5 text-zinc-300 mr-auto border border-white/10"
                  )}
                >
                  <p className="whitespace-pre-wrap break-words leading-relaxed overflow-hidden">{m.content}</p>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          <div className="p-4 border-t border-white/5 bg-black/40 relative">
            {showApproval && (
              <div className="absolute bottom-full left-4 right-4 mb-4 bg-red-500/10 border border-red-500/20 rounded-xl p-4 backdrop-blur-xl">
                <div className="flex items-center gap-2 text-red-500 mb-2">
                  <ShieldAlert size={16} /> 
                  <span className="text-xs font-bold uppercase tracking-widest">Approval Required</span>
                </div>
                <p className="text-xs text-red-200 mb-4">The agent is requesting to use <strong>{showApproval.tool}</strong>.</p>
                <div className="flex items-center gap-3">
                  <button 
                    onClick={() => handleApproveDecision(true)} 
                    className="flex-1 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
                  >
                    Confirm & Execute
                  </button>
                  <button 
                    onClick={() => handleApproveDecision(false)} 
                    className="px-4 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl text-[10px] font-black uppercase tracking-widest transition-all"
                  >
                    Abort
                  </button>
                </div>
              </div>
            )}
            
             <div className="flex items-center gap-3">
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
                 className="p-3 bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white rounded-xl transition-all border border-white/10 shrink-0 disabled:opacity-50"
                 title="Upload Document"
               >
                 {isUploading ? <Loader2 size={18} className="animate-spin" /> : <Paperclip size={18} />}
               </button>
               <input
                 className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:ring-1 focus:ring-blue-500 text-sm text-white placeholder-zinc-500 transition-all disabled:opacity-50"
                 placeholder="Assign task coordinates to ASTRA..."
                 value={input}
                 disabled={isStreaming}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && !isStreaming && runAgentTask(input)}
               />
               {isStreaming ? (
                 <button 
                   onClick={handleStopGeneration}
                   className="bg-red-600 hover:bg-red-500 text-white p-3 rounded-xl transition-colors shrink-0 animate-pulse"
                   title="Stop generation"
                 >
                   <StopCircle size={18} />
                 </button>
               ) : (
                 <button 
                   onClick={() => runAgentTask(input)}
                   disabled={!input.trim() || isStreaming}
                   className="bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl transition-colors shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                 >
                   <Send size={18} />
                 </button>
               )}
             </div>
          </div>
        </div>

        {/* Right: Agent Avatar Visor */}
        <div className="w-1/3 min-w-[300px] min-h-0 flex flex-col gap-6">
          <div className="glass flex-1 rounded-[2rem] border border-white/5 p-6 flex items-center justify-center relative overflow-hidden group">
            {/* Visual background syncs with state */}
            <div className={cn("absolute inset-0 opacity-10 transition-colors duration-1000", statusColor)} />
            
            <div className="flex flex-col items-center gap-6 z-10">
               {/* Minimal 3D placeholder */}
               <div className="relative">
                  <div className="w-32 h-32 rounded-full glass border border-white/10 flex items-center justify-center overflow-hidden">
                     <Cpu size={48} className={cn("transition-colors duration-500", 
                        avatarState === "idle" ? "text-emerald-500" :
                        avatarState === "thinking" ? "text-purple-500" :
                        avatarState === "typing" ? "text-blue-500 animate-bounce" :
                        avatarState === "waking" ? "text-orange-500 animate-pulse" :
                        "text-amber-500 animate-pulse"
                     )} />
                  </div>
                  {/* Orbit rings */}
                  <div className={cn("absolute -inset-4 border border-dashed rounded-full transition-all duration-[3000ms]",
                     statusColor.replace("bg-", "border-"),
                     avatarState !== "idle" ? "animate-spin" : ""
                  )} />
               </div>

               <div className="flex flex-col items-center gap-1">
                 <span className="text-[10px] uppercase tracking-widest text-zinc-500">Agent Status</span>
                 <span className={cn("text-lg font-black uppercase tracking-widest transition-colors", statusColor.replace("bg-", "text-"))}>
                   {avatarState}
                 </span>
               </div>
            </div>
          </div>
          
          {/* Debug Console — Internal Telemetry */}
          <div className="h-48 rounded-[2rem] bg-black border border-white/5 p-6 relative overflow-hidden flex flex-col">
             <div className="flex items-center gap-2 mb-4 text-zinc-600">
                <Terminal size={14} />
                <span className="text-[10px] font-bold uppercase tracking-widest">Internal Telemetry</span>
             </div>
             <div className="text-[10px] font-mono text-emerald-500 flex-1 overflow-y-auto space-y-1">
                <p className="animate-pulse">[SYSTEM] Stream Connection Valid</p>
                <p>[EVENT] Last broadcast mapping: {avatarState.toUpperCase()}</p>
                <AnimatePresence>
                  {thinkingText && (
                    <motion.p
                      key="thinking"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className={cn(
                        "mt-1",
                        avatarState === "waking" ? "text-orange-400" : "text-purple-400"
                      )}
                    >
                      [{avatarState === "waking" ? "WAKING" : "THOUGHT"}] {thinkingText}
                    </motion.p>
                  )}
                </AnimatePresence>
                {isStreaming && (
                  <p className="text-blue-400 animate-pulse">[STREAM] Active SSE connection — receiving events</p>
                )}
             </div>
          </div>
        </div>
      </div>
    </div>
  );
};
