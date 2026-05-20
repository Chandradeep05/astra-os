"use client";

import React, { useEffect, useState } from "react";
import { 
  Activity, 
  Play, 
  Clock, 
  Search, 
  Loader2, 
  CheckCircle, 
  XCircle, 
  FileText, 
  RefreshCw,
  Sliders,
  Terminal,
  Cpu,
  AlertTriangle
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface BackgroundTasksProps {
  projectId: string;
}

interface TaskLog {
  id: number;
  project_id: string;
  action_type: string;
  details: string;
  created_at: string;
}

interface WorkflowItem {
  id: string;
  name: string;
  description: string;
  status: string;
  last_run: string | null;
  created_at: string;
}

export const BackgroundTasks = ({ projectId }: BackgroundTasksProps) => {
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedActionType, setSelectedActionType] = useState<string>("ALL");
  
  // Auto-polling interval
  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [triggeringWorkflowId, setTriggeringWorkflowId] = useState<string | null>(null);

  const fetchData = async (showLoading = false) => {
    if (showLoading) setIsLoading(true);
    else setIsRefreshing(true);
    
    try {
      const data = await api.getTasks(projectId);
      setLogs(data.logs || []);
      setWorkflows(data.workflows || []);
    } catch (err) {
      console.error("Failed to load tasks data:", err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData(true);
  }, [projectId]);

  // Handle polling
  useEffect(() => {
    if (!pollingEnabled) return;
    
    const interval = setInterval(() => {
      fetchData();
    }, 6000); // Poll every 6s

    return () => clearInterval(interval);
  }, [projectId, pollingEnabled]);

  const handleTriggerWorkflow = async (workflowId: string) => {
    setTriggeringWorkflowId(workflowId);
    try {
      await api.triggerWorkflow(workflowId);
      // Wait a moment then refresh data
      setTimeout(() => {
        fetchData();
        setTriggeringWorkflowId(null);
      }, 1000);
    } catch (err) {
      console.error(err);
      alert("Failed to trigger workflow execution.");
      setTriggeringWorkflowId(null);
    }
  };

  const getActionBadgeStyle = (actionType: string) => {
    const type = actionType.toUpperCase();
    if (type.includes("ERROR") || type.includes("FAILED")) {
      return "bg-red-500/10 text-red-400 border-red-500/20";
    }
    if (type.includes("COMPLETED") || type.includes("SUCCESS")) {
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    }
    if (type.includes("START") || type.includes("INGESTION") || type.includes("EXECUTION")) {
      return "bg-blue-500/10 text-blue-400 border-blue-500/20";
    }
    if (type.includes("TOOL")) {
      return "bg-purple-500/10 text-purple-400 border-purple-500/20";
    }
    return "bg-zinc-500/10 text-zinc-400 border-zinc-500/20";
  };

  const getActionIcon = (actionType: string) => {
    const type = actionType.toUpperCase();
    if (type.includes("ERROR") || type.includes("FAILED")) {
      return <XCircle className="text-red-400 shrink-0" size={16} />;
    }
    if (type.includes("COMPLETED") || type.includes("SUCCESS")) {
      return <CheckCircle className="text-emerald-400 shrink-0" size={16} />;
    }
    if (type.includes("TOOL")) {
      return <Cpu className="text-purple-400 shrink-0" size={16} />;
    }
    return <Clock className="text-zinc-500 shrink-0" size={16} />;
  };

  // Get unique action types for filter
  const actionTypes = ["ALL", ...Array.from(new Set(logs.map(l => l.action_type)))];

  const filteredLogs = logs.filter(log => {
    const matchesSearch = log.details.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          log.action_type.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = selectedActionType === "ALL" || log.action_type === selectedActionType;
    return matchesSearch && matchesType;
  });

  return (
    <div className="h-full w-full overflow-y-auto bg-[#09090b] p-8 lg:p-12 space-y-12 pb-24">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-emerald-500">
            <Activity size={16} />
            <span className="text-[10px] font-black uppercase tracking-[0.3em]">Background Engine</span>
          </div>
          <h1 className="text-4xl font-black text-white tracking-tight italic uppercase">
            Execution <span className="text-zinc-500 not-italic font-light">Engine</span>
          </h1>
          <p className="text-zinc-400 text-sm max-w-2xl">
            Monitor active workflows, long-running agent reasoning logs, document ingestions, and background processes in real-time.
          </p>
        </div>

        {/* Refresh & Polling controls */}
        <div className="flex items-center gap-4 bg-zinc-950/40 p-2.5 rounded-2xl border border-white/5 shrink-0 self-start sm:self-center">
          <div className="flex items-center gap-2 px-1 text-xs">
            <span className="text-zinc-500 font-semibold">Live Polling</span>
            <button
              onClick={() => setPollingEnabled(!pollingEnabled)}
              className={cn(
                "w-8 h-5 rounded-full p-0.5 transition-all duration-300 flex items-center cursor-pointer",
                pollingEnabled ? "bg-emerald-500 justify-end" : "bg-zinc-800 justify-start"
              )}
            >
              <div className="w-3.5 h-3.5 rounded-full bg-white shadow-sm" />
            </button>
          </div>
          
          <div className="h-4 w-px bg-white/5" />
          
          <button
            onClick={() => fetchData()}
            disabled={isRefreshing || isLoading}
            className="p-1.5 hover:bg-white/5 rounded-lg text-zinc-400 hover:text-white transition-colors flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider"
          >
            <RefreshCw size={14} className={cn((isRefreshing || isLoading) && "animate-spin")} />
            REFRESH
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Left Columns: Audit Trail / Logs */}
        <div className="xl:col-span-2 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <h2 className="text-xs font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
              <Terminal size={14} className="text-emerald-500" />
              Agent Audit Trail & Execution Logs
            </h2>

            {/* Quick Filters */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 max-w-full">
              <select
                value={selectedActionType}
                onChange={(e) => setSelectedActionType(e.target.value)}
                className="bg-zinc-900 border border-white/5 text-[11px] rounded-lg px-2 py-1 text-zinc-400 font-bold focus:ring-0 focus:border-white/10"
              >
                {actionTypes.map(t => (
                  <option key={t} value={t}>{t === "ALL" ? "All Logs" : t}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-4 top-3 text-zinc-500" size={16} />
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search audit details or actions..."
              className="w-full bg-white/5 border border-white/5 rounded-2xl pl-12 pr-4 py-2.5 text-xs text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 transition-all"
            />
          </div>

          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <Loader2 className="animate-spin text-zinc-600" size={32} />
              <span className="text-sm text-zinc-500 font-medium">Streaming execution records...</span>
            </div>
          ) : filteredLogs.length === 0 ? (
            <div className="glass border border-white/5 rounded-[2rem] p-16 text-center space-y-4">
              <div className="w-12 h-12 rounded-full bg-white/[0.02] border border-white/5 flex items-center justify-center mx-auto">
                <Terminal className="text-zinc-600" size={20} />
              </div>
              <p className="text-zinc-500 text-sm font-semibold">No execution logs matched filters</p>
            </div>
          ) : (
            <div className="glass border border-white/5 rounded-[2rem] overflow-hidden">
              <div className="max-h-[600px] overflow-y-auto divide-y divide-white/5 font-mono text-[11px] pr-1">
                <AnimatePresence initial={false}>
                  {filteredLogs.map((log) => (
                    <motion.div 
                      key={log.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="p-4 flex items-start gap-4 hover:bg-white/[0.01] transition-all"
                    >
                      {/* Icon */}
                      {getActionIcon(log.action_type)}

                      {/* Content */}
                      <div className="flex-1 space-y-1.5 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "px-2 py-0.5 rounded-full border text-[9px] font-bold tracking-tight shrink-0",
                            getActionBadgeStyle(log.action_type)
                          )}>
                            {log.action_type}
                          </span>
                          
                          <span className="text-[9px] text-zinc-600 shrink-0">
                            {new Date(log.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        <p className="text-zinc-300 font-semibold leading-relaxed break-words">{log.details}</p>
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Workflow Runners */}
        <div className="space-y-6">
          <h2 className="text-xs font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
            <Sliders size={14} className="text-blue-500" />
            Registered Workflows
          </h2>

          {isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="animate-spin text-zinc-700" size={24} />
            </div>
          ) : workflows.length === 0 ? (
            <div className="glass border border-white/5 rounded-[2rem] p-8 text-center space-y-2">
              <AlertTriangle className="text-zinc-600 mx-auto" size={20} />
              <p className="text-xs font-semibold text-zinc-500">No workflows configured</p>
              <p className="text-[10px] text-zinc-600">Workflows can be registered via the API or Workflow engine component.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {workflows.map((wf) => (
                <div 
                  key={wf.id}
                  className="glass p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-all space-y-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-bold text-white tracking-tight">{wf.name}</h4>
                      <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{wf.description || "No description provided."}</p>
                    </div>

                    <span className={cn(
                      "px-2 py-0.5 rounded-full border text-[9px] font-bold uppercase shrink-0",
                      wf.status === "active" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                    )}>
                      {wf.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-4 pt-3 border-t border-white/5 text-[10px]">
                    <div className="flex items-center gap-1.5 text-zinc-500">
                      <Clock size={12} />
                      <span>Last run: {wf.last_run ? new Date(wf.last_run).toLocaleString() : "Never"}</span>
                    </div>

                    <button
                      onClick={() => handleTriggerWorkflow(wf.id)}
                      disabled={triggeringWorkflowId === wf.id}
                      className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white font-bold tracking-wider flex items-center gap-1 hover:scale-105 active:scale-95 transition-all disabled:opacity-50"
                    >
                      {triggeringWorkflowId === wf.id ? (
                        <Loader2 className="animate-spin" size={10} />
                      ) : (
                        <Play size={10} fill="currentColor" />
                      )}
                      RUN NOW
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>

    </div>
  );
};
