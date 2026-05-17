"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Paperclip,
  Sparkles,
  User,
  Bot,
  Trash2,
  Copy,
  Loader2,
  Globe,
  Code,
  Cpu,
  Terminal,
  Mic,
  MicOff,
  Volume2,
  Download,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useWebLLM } from "../hooks/useWebLLM";

// Derive API base from environment — same source of truth as api.ts
const API_HOST = process.env.NEXT_PUBLIC_API_URL
  ? process.env.NEXT_PUBLIC_API_URL.replace("/api/v1", "")
  : "http://127.0.0.1:8000";

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  thoughts?: string[];
  citations?: string[];
  artifact_url?: string;
  file_preview_url?: string;
  file_type?: string;
}

interface ChatInterfaceProps {
  project_id: string;
  project_name?: string;
}

export const ChatInterface = ({
  project_id,
  project_name,
}: ChatInterfaceProps) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: `Welcome to ASTRA OS. Active Workspace: ${project_name || "Primary Core"}. How can I assist you today?`,
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { engine, isInitializing, progress, initWebLLM } = useWebLLM();

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Fix #6: Abort in-flight streams on unmount or project switch
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [project_id]);

  // Load history when project changes
  useEffect(() => {
    const loadHistory = async () => {
      if (!project_id || project_id === "dashboard") {
        setMessages([
          {
            role: "assistant",
            content:
              "Select a context from the sidebar or start a New Context to begin orchestration.",
          },
        ]);
        return;
      }
      try {
        const proj = await api.getProject(project_id);
        if (proj.history && proj.history.length > 0) {
          setMessages(proj.history as Message[]);
        } else {
          setMessages([
            {
              role: "assistant",
              content: `Neural Context Initialized: ${project_name || "New Workspace"}. How can ASTRA assist you?`,
            },
          ]);
        }
      } catch (error) {
        console.warn("Failed to load project history", error);
        setMessages([
          {
            role: "assistant",
            content:
              "Astra Core: Ready. Context initialized.",
          },
        ]);
      }
    };
    loadHistory();
  }, [project_id, project_name]);

  // Auto-save history (debounced)
  useEffect(() => {
    if (
      messages.length <= 1 ||
      isLoading ||
      !project_id ||
      project_id === "dashboard"
    )
      return;

    const timeout = setTimeout(async () => {
      try {
        await api.updateProject(project_id, { history: messages });
      } catch (error) {
        console.warn("Failed to auto-save history", error);
      }
    }, 5000);

    return () => clearTimeout(timeout);
  }, [messages, isLoading, project_id]);

  const [expandedThoughts, setExpandedThoughts] = useState<{
    [key: number]: boolean;
  }>({});
  const [activeAgent, setActiveAgent] = useState<string>("ASTRA Prime");
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Initialize Speech Recognition
  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)
    ) {
      const SpeechRecognition =
        (window as any).webkitSpeechRecognition ||
        (window as any).SpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;

      recognitionRef.current.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsListening(false);
      };

      recognitionRef.current.onerror = () => setIsListening(false);
      recognitionRef.current.onend = () => setIsListening(false);
    }
  }, []);

  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
    } else {
      setIsListening(true);
      recognitionRef.current?.start();
    }
  };

  const speakResponse = (text: string) => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 0.9;
      window.speechSynthesis.speak(utterance);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input };
    const currentMessages = [...messages, userMessage];

    // Assign a unique ID to this response placeholder to prevent bleeding
    // when two requests are in-flight simultaneously
    const msgId = Date.now().toString() + Math.random().toString(36).slice(2, 7);

    // Add user message + empty assistant placeholder
    setMessages([
      ...currentMessages,
      { id: msgId, role: "assistant", content: "", thoughts: [] },
    ]);
    setInput("");
    setIsLoading(true);

    // Create abort controller for this request
    const abortController = new AbortController();
    abortRef.current = abortController;

    // HYBRID ROUTER: If WebLLM is loaded, use it natively. Otherwise fallback to local API layer.
    if (engine) {
      setActiveAgent("BROWSER NATIVE (WebGPU)");
      try {
        const stream = await engine.chat.completions.create({
          messages: currentMessages as any,
          stream: true,
        });

        for await (const chunk of stream) {
          if (abortController.signal.aborted) break;
          const textChunk = chunk.choices[0]?.delta?.content || "";
          
          setMessages((prev) => {
            const newMsgs = [...prev];
            const lastMsg = newMsgs[newMsgs.length - 1];
            if (lastMsg.role === "assistant") {
              newMsgs[newMsgs.length - 1] = {
                ...lastMsg,
                content: lastMsg.content + textChunk,
              };
            }
            return newMsgs;
          });
        }
      } catch (error: any) {
        if (error.name !== "AbortError") {
          setMessages((prev) => {
            const newMsgs = [...prev];
            newMsgs[newMsgs.length - 1] = {
              ...newMsgs[newMsgs.length - 1],
              content: `⚠️ WebGL Error: ${error.message}`,
            };
            return newMsgs;
          });
        }
      } finally {
        setIsLoading(false);
      }
      return;
    }

    try {
      await api.streamMessage(
        {
          messages: currentMessages,
          project_id: project_id,
        },
        (chunk) => {
          if (chunk.type === "meta") {
            if (chunk.engine) setActiveAgent("LOCAL NODE (" + chunk.engine + ")");
          } else if (chunk.type === "answer" || chunk.type === "content") {
            // Match by message ID to prevent concurrent stream bleeding
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === msgId);
              if (idx === -1) return prev;
              const newMsgs = [...prev];
              newMsgs[idx] = {
                ...newMsgs[idx],
                content: newMsgs[idx].content + (chunk.content || ""),
              };
              return newMsgs;
            });
          } else if (chunk.type === "thought") {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === msgId);
              if (idx === -1) return prev;
              const newMsgs = [...prev];
              newMsgs[idx] = {
                ...newMsgs[idx],
                thoughts: [...(newMsgs[idx].thoughts || []), chunk.content],
              };
              return newMsgs;
            });
          } else if (chunk.type === "error") {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === msgId);
              if (idx === -1) return prev;
              const newMsgs = [...prev];
              newMsgs[idx] = {
                ...newMsgs[idx],
                content: `⚠️ ${chunk.content}`,
              };
              return newMsgs;
            });
          } else if (chunk.type === "artifact") {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === msgId);
              if (idx === -1) return prev;
              const newMsgs = [...prev];
              newMsgs[idx] = {
                ...newMsgs[idx],
                artifact_url: chunk.url,
              };
              return newMsgs;
            });
          }
          // Ignore "done" chunks — they just signal stream end
        },
        abortController.signal
      );
    } catch (error: any) {
      if (error.name === "AbortError") return; // User cancelled
      console.error("Stream error:", error);
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = {
          ...newMsgs[newMsgs.length - 1],
          content:
            "⚠️ Could not connect to Local ASTRA Node. Click 'Initialize WebGPU' to run without a backend.",
        };
        return newMsgs;
      });
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  };

  const handleStopGeneration = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", project_id);

    try {
      const response = await fetch(
        `${API_HOST}/api/v1/documents/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) throw new Error("Upload failed");
      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `✅ ${data.filename.toUpperCase()} INGESTED: ASTRA has processed this file into your workspace memory.`,
          file_preview_url: file.type.startsWith("image/") ? `${API_HOST}/api/v1/documents/preview/${data.file_id}` : undefined,
          file_type: file.type
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "⚠️ Document ingestion failed. Check that the backend is running.",
        },
      ]);
    } finally {
      setIsLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#08080a] relative overflow-hidden">
      {/* Dynamic Background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-20%,#1e1b4b,transparent)] opacity-40 pointer-events-none" />

      {/* Chat Header */}
      <header className="h-20 border-b border-white/10 flex items-center justify-between px-8 backdrop-blur-2xl bg-black/40 sticky top-0 z-30 transition-all">
        <div className="flex items-center gap-5">
          <div className="relative">
            <div
              className={cn(
                "w-3 h-3 rounded-full transition-all duration-700 relative z-10",
                isLoading
                  ? "bg-blue-500 animate-ping"
                  : "bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)]"
              )}
            />
            <div className="absolute inset-0 bg-blue-500/20 blur-md rounded-full animate-pulse" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black text-blue-500 uppercase tracking-[0.3em]">
                Neural Interface v2.0
              </span>
              <span className="text-[8px] px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 font-mono">
                PRO
              </span>
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
              {isLoading
                ? "ORCHESTRATING..."
                : project_name || "ASTRA OS CORE"}
              {!isLoading && (
                <span className="text-xs font-normal text-zinc-500 font-mono">
                  [{activeAgent}]
                </span>
              )}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Agent Status HUD */}
          <div className="hidden md:flex flex-col items-end mr-4 font-mono">
            <span className="text-[9px] text-zinc-600 uppercase">
              Engine: {engine ? "WebGPU Native" : "Local Node"}
            </span>
            <span className="text-[9px] text-emerald-500/80 uppercase">
              Status: {isLoading ? "Streaming" : "Ready"}
            </span>
          </div>

          {progress && (
            <div className="text-[10px] font-mono text-blue-400 mr-4 animate-pulse">
              {progress}
            </div>
          )}

          {!engine && (
            <button
              onClick={initWebLLM}
              disabled={isInitializing}
              className="px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-xl transition-all border border-blue-500/20 text-[11px] font-black uppercase tracking-widest flex items-center gap-2"
            >
              {isInitializing ? (
                <><Loader2 size={14} className="animate-spin" /> Ingesting Weights...</>
              ) : (
                <><Cpu size={14} /> Init WebGPU</>
              )}
            </button>
          )}

          <button
            onClick={() =>
              setMessages([
                {
                  role: "assistant",
                  content: "Memory purged. Ready for new input.",
                },
              ])
            }
            className="p-2.5 hover:bg-white/5 rounded-xl transition-all text-zinc-500 hover:text-white border border-white/0 hover:border-white/10 group"
            title="Clear Chat"
          >
            <Trash2
              size={18}
              className="group-hover:scale-110 transition-transform"
            />
          </button>
        </div>
      </header>

      {/* Message Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 lg:p-12 space-y-12 scrollbar-hide relative"
      >
        <AnimatePresence mode="popLayout">
          {messages.map((msg, idx) => (
            <motion.div
              key={`msg-${idx}`}
              initial={{ opacity: 0, y: 20, filter: "blur(10px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
              className={cn(
                "flex gap-8 max-w-5xl transition-all duration-500",
                msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
              )}
            >
              <div
                className={cn(
                  "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border transition-all duration-500 relative group",
                  msg.role === "user"
                    ? "bg-white text-black border-white/20 shadow-2xl"
                    : "bg-gradient-to-br from-zinc-800 to-black text-white border-white/10 shadow-2xl overflow-hidden"
                )}
              >
                {msg.role === "user" ? (
                  <User size={24} />
                ) : (
                  <Cpu size={24} className="text-blue-400" />
                )}
                {msg.role === "assistant" && (
                  <div className="absolute inset-0 bg-blue-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
              </div>

              <div className="flex flex-col gap-3 min-w-0 flex-1">
                <div
                  className={cn(
                    "relative px-6 py-5 rounded-[2rem] text-[16px] leading-[1.6] shadow-2xl border transition-all overflow-hidden",
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-tr-sm border-blue-400/30"
                      : "bg-white/[0.03] text-zinc-300 border-white/10 backdrop-blur-xl rounded-tl-sm"
                  )}
                >
                  {/* Glass shimmer for assistant */}
                  {msg.role === "assistant" && (
                    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                  )}

                  <div className="relative z-10 prose prose-invert prose-p:leading-relaxed prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10 max-w-none text-[15px]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>

                  {msg.file_preview_url && (
                    <div className="mt-4 rounded-2xl overflow-hidden border border-white/10 shadow-lg relative group/preview">
                      {msg.file_type?.startsWith("image/") ? (
                        <img 
                          src={msg.file_preview_url} 
                          alt="Uploaded Content" 
                          className="w-full max-h-[300px] object-contain bg-black/40"
                        />
                      ) : (
                        <div className="p-8 bg-white/5 flex flex-col items-center gap-3">
                          <Paperclip size={32} className="text-blue-500" />
                          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{msg.file_type}</span>
                        </div>
                      )}
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover/preview:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-sm">
                        <span className="text-[10px] font-black text-white uppercase tracking-[0.3em]">Neural Scan: Completed</span>
                      </div>
                    </div>
                  )}

                  {msg.thoughts && msg.thoughts.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/5 relative z-10">
                      <button
                        onClick={() =>
                          setExpandedThoughts((prev) => ({
                            ...prev,
                            [idx]: !prev[idx],
                          }))
                        }
                        className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2 hover:text-blue-400 transition-colors"
                      >
                        <Terminal size={12} />
                        {expandedThoughts[idx] ? "Hide" : "View"} Thought
                        Process
                      </button>
                      {expandedThoughts[idx] && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          className="mt-3 space-y-2 overflow-hidden"
                        >
                          {msg.thoughts.map(
                            (thought: string, tidx: number) => (
                              <div
                                key={tidx}
                                className="text-[11px] font-mono text-zinc-500 border-l border-blue-500/30 pl-3 py-1"
                              >
                                {">"} {thought}
                              </div>
                            )
                          )}
                        </motion.div>
                      )}
                    </div>
                  )}

                  {msg.role === "assistant" && msg.content && (
                    <div className="absolute bottom-4 right-4 flex items-center gap-2 z-10">
                      {msg.artifact_url && (
                        <a
                          href={`${API_HOST}${msg.artifact_url}`}
                          download
                          className="bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 p-2 rounded-lg transition-all flex items-center gap-2 text-[10px] font-bold border border-emerald-500/20"
                        >
                          <Download size={14} /> DOWNLOAD
                        </a>
                      )}
                      <button
                        onClick={() => speakResponse(msg.content)}
                        className="text-zinc-600 hover:text-blue-400 transition-colors p-1"
                        title="Vocalize Response"
                      >
                        <Volume2 size={14} />
                      </button>
                    </div>
                  )}

                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap gap-2 relative z-10">
                      <span className="text-[10px] text-zinc-500 font-bold uppercase w-full mb-1">
                        Sources
                      </span>
                      {msg.citations.map((url: string, cidx: number) => (
                        <a
                          key={cidx}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 px-2 py-1 rounded border border-blue-500/10 truncate max-w-[150px]"
                        >
                          {new URL(url).hostname}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          ))}

          {isLoading && (
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex gap-8 max-w-4xl mr-auto"
            >
              <div className="w-12 h-12 rounded-2xl bg-white/5 text-white border border-white/10 flex items-center justify-center animate-pulse">
                <div className="flex gap-0.5 items-center">
                  {[1, 2, 3].map((i) => (
                    <motion.div
                      key={i}
                      animate={{ height: [4, 12, 4] }}
                      transition={{
                        repeat: Infinity,
                        duration: 0.6,
                        delay: i * 0.1,
                      }}
                      className="w-1 bg-blue-500 rounded-full"
                    />
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-4 w-full">
                <div className="bg-white/[0.02] border border-white/10 px-6 py-5 rounded-[2rem] rounded-tl-sm backdrop-blur-xl flex flex-col gap-3 max-w-md shadow-2xl">
                  <div className="flex items-center gap-3">
                    <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" />
                    <span className="text-sm font-bold text-blue-400 uppercase tracking-widest">
                      Neural Link: ACTIVE
                    </span>
                  </div>
                  <div className="space-y-1.5 overflow-hidden">
                    <div className="text-[10px] font-mono text-zinc-600 animate-pulse">
                      {">> "}AGENT: {activeAgent.toUpperCase()}
                    </div>
                    <div className="text-[10px] font-mono text-zinc-600 animate-pulse">
                      {">> "}STREAMING RESPONSE...
                    </div>
                  </div>
                  <button
                    onClick={handleStopGeneration}
                    className="mt-2 text-[10px] font-bold text-red-400 hover:text-red-300 uppercase tracking-widest transition-colors"
                  >
                    ■ Stop Generation
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input Area */}
      <div className="p-8 border-t border-white/5 bg-[#09090b] relative z-20">
        <div className="max-w-5xl mx-auto relative group">
          <div className="absolute inset-0 bg-white/[0.02] blur-3xl rounded-full opacity-0 group-focus-within:opacity-100 transition-opacity duration-1000" />

          <div className="relative glass rounded-[2rem] p-3 flex items-end gap-3 border border-white/5 group-focus-within:border-white/20 transition-all duration-500 shadow-2xl">
            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              onChange={handleFileUpload}
              accept=".pdf,.docx,.xlsx,.txt,.md,.json,.png,.jpg,.jpeg,.wav,.mp3"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-3 text-zinc-500 hover:text-white hover:bg-white/5 rounded-2xl transition-all group/icon"
            >
              <Paperclip
                size={22}
                className="group-hover/icon:-rotate-45 transition-transform duration-300"
              />
            </button>
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !isLoading) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isLoading}
              placeholder="Message Astra Assistant..."
              className="w-full bg-transparent border-none focus:ring-0 focus:outline-none resize-none text-[15px] py-4 px-2 text-white placeholder:text-zinc-600 disabled:opacity-50 font-medium"
            />

            <button
              onClick={toggleListening}
              className={cn(
                "p-4 rounded-2xl transition-all active:scale-95",
                isListening
                  ? "bg-red-500/20 text-red-500 animate-pulse"
                  : "text-zinc-500 hover:text-white hover:bg-white/5"
              )}
            >
              {isListening ? <MicOff size={20} /> : <Mic size={20} />}
            </button>

            <button
              onClick={isLoading ? handleStopGeneration : handleSend}
              disabled={!isLoading && !input.trim()}
              className={cn(
                "p-4 rounded-2xl transition-all active:scale-95 disabled:opacity-50 shadow-[0_0_20px_rgba(255,255,255,0.1)] group/send",
                isLoading
                  ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                  : "bg-white text-black hover:bg-zinc-200"
              )}
            >
              {isLoading ? (
                <div className="w-5 h-5 flex items-center justify-center">
                  <div className="w-3 h-3 bg-red-400 rounded-sm" />
                </div>
              ) : (
                <Send
                  size={20}
                  className="group-hover/send:translate-x-0.5 group-hover/send:-translate-y-0.5 transition-transform"
                />
              )}
            </button>
          </div>

          {/* Feature Badges */}
          <div className="flex justify-center mt-4 gap-8">
            <Badge
              icon={<Sparkles size={12} />}
              label="Local AI"
              color="emerald"
            />
            <Badge
              icon={
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              }
              label="Private"
              color="blue"
            />
            <Badge icon={<Globe size={12} />} label="Offline" color="purple" />
            <Badge
              icon={<Code size={12} />}
              label="No Limits"
              color="orange"
            />
          </div>
        </div>
      </div>
    </div>
  );
};

const Badge = ({
  icon,
  label,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
}) => (
  <div className="flex items-center gap-2 group cursor-default">
    <div
      className={cn(
        "opacity-40 group-hover:opacity-100 transition-opacity",
        color === "emerald" && "text-emerald-500",
        color === "blue" && "text-blue-500",
        color === "purple" && "text-purple-500",
        color === "orange" && "text-orange-500"
      )}
    >
      {icon}
    </div>
    <span className="text-[10px] uppercase font-bold tracking-[0.25em] text-zinc-600 group-hover:text-zinc-400 transition-colors">
      {label}
    </span>
  </div>
);
