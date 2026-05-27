"use client";

import React, { useEffect, useState } from "react";
import { 
  Calendar, 
  Clock, 
  Plus, 
  Trash2, 
  Play, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Activity, 
  Pause,
  AlertTriangle
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, ScheduledTask, Project } from "@/lib/api";
import { cn } from "@/lib/utils";

export const ScheduledTasks = () => {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form State
  const [name, setName] = useState("");
  const [cronExpression, setCronExpression] = useState("0 9 * * 1-5");
  const [agentPrompt, setAgentPrompt] = useState("");
  const [projectId, setProjectId] = useState("default");
  const [enabled, setEnabled] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const fetchData = async () => {
    try {
      setIsLoading(true);
      const [allTasks, allProjects] = await Promise.all([
        api.listScheduledTasks(),
        api.getProjects()
      ]);
      setTasks(allTasks);
      setProjects(allProjects);
    } catch (err: any) {
      console.error("Failed to load scheduler data:", err);
      setErrorMsg("Failed to load scheduled tasks.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !cronExpression.trim() || !agentPrompt.trim()) {
      setErrorMsg("Please fill in all required fields.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg("");
    setSuccessMsg("");

    try {
      const newTask = await api.addScheduledTask({
        name: name.trim(),
        cron_expression: cronExpression.trim(),
        agent_prompt: agentPrompt.trim(),
        project_id: projectId,
        enabled
      });
      setTasks((prev) => [...prev, newTask]);
      setName("");
      setAgentPrompt("");
      setSuccessMsg("Scheduled task created successfully!");
      // Auto dismiss success msg
      setTimeout(() => setSuccessMsg(""), 3000);
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "Failed to create scheduled task. Check cron expression format.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleTask = async (task: ScheduledTask) => {
    try {
      const updated = await api.updateScheduledTask(task.id, {
        enabled: !task.enabled
      });
      setTasks((prev) =>
        prev.map((t) => (t.id === task.id ? { ...t, enabled: updated.enabled, next_run: updated.next_run } : t))
      );
    } catch (err) {
      console.error("Failed to toggle task:", err);
      alert("Failed to toggle scheduled task status.");
    }
  };

  const handleDeleteTask = async (id: number) => {
    if (!confirm("Are you sure you want to delete this scheduled agent?")) return;
    try {
      await api.deleteScheduledTask(id);
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      console.error("Failed to delete task:", err);
      alert("Failed to delete scheduled task.");
    }
  };

  const handleTriggerTask = async (id: number) => {
    try {
      alert("Task manually triggered! Execution started in the background.");
      await api.triggerScheduledTask(id);
      // Reload tasks list to reflect last run time if immediate
      fetchData();
    } catch (err) {
      console.error("Failed to trigger task:", err);
      alert("Failed to trigger task execution.");
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <Loader2 className="animate-spin text-emerald-500" size={32} />
        <span className="text-sm font-semibold tracking-widest text-zinc-500 uppercase">Loading Scheduled Agents...</span>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto px-8 lg:px-10 py-8 space-y-10 scrollbar-hide">
      
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-6">
        <div className="space-y-1">
          <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
            <Calendar className="text-emerald-500" size={32} />
            Scheduled Agents
          </h1>
          <p className="text-sm text-zinc-500">
            Orchestrate autonomous agent cron runs. Run periodic document audits, system sweeps, or data backups.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-8">
        
        {/* Left Column: Form (xl:span-2) */}
        <div className="xl:col-span-2 space-y-6">
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
              <Activity size={16} className="text-emerald-500" />
              Configure Recurring Agent
            </h3>

            <form onSubmit={handleAddTask} className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Agent Job Name</label>
                <input 
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Weekly Document Sync"
                  className="w-full bg-white/5 border border-white/5 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Context Project</label>
                  <select 
                    value={projectId}
                    onChange={(e) => setProjectId(e.target.value)}
                    className="w-full bg-zinc-950 border border-white/5 rounded-2xl px-4 py-3 text-sm text-zinc-400 focus:ring-0 focus:border-white/10"
                  >
                    <option value="default">default</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Cron Expression</label>
                  <input 
                    type="text"
                    value={cronExpression}
                    onChange={(e) => setCronExpression(e.target.value)}
                    placeholder="*/10 * * * * (Every 10 min)"
                    className="w-full bg-white/5 border border-white/5 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Agent Execution Prompt</label>
                <textarea 
                  value={agentPrompt}
                  onChange={(e) => setAgentPrompt(e.target.value)}
                  placeholder="Summarize new files added in the last 24 hours and write audit_log.md in the workspace."
                  rows={6}
                  className="w-full bg-white/5 border border-white/5 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 resize-none"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input 
                  type="checkbox"
                  id="enabled"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="rounded bg-zinc-950 border border-white/5 text-emerald-500 focus:ring-0"
                />
                <label htmlFor="enabled" className="text-xs font-semibold text-zinc-300 cursor-pointer select-none">
                  Enable Cron Schedule Immediately
                </label>
              </div>

              <AnimatePresence>
                {errorMsg && (
                  <motion.div 
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs flex items-center gap-2"
                  >
                    <AlertTriangle size={14} className="shrink-0" />
                    <span>{errorMsg}</span>
                  </motion.div>
                )}
                {successMsg && (
                  <motion.div 
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl text-xs flex items-center gap-2"
                  >
                    <CheckCircle2 size={14} className="shrink-0" />
                    <span>{successMsg}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              <button 
                type="submit"
                disabled={isSubmitting}
                className="w-full py-3.5 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-2xl text-sm hover:scale-105 active:scale-95 transition-all flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(16,185,129,0.2)] disabled:opacity-50"
              >
                {isSubmitting ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <>
                    <Plus size={18} />
                    Schedule Agent
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: List (xl:span-3) */}
        <div className="xl:col-span-3 space-y-6">
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <div className="flex items-center justify-between border-b border-white/5 pb-4">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Clock size={16} className="text-emerald-500" />
                Active Recurring Jobs ({tasks.length})
              </h3>
            </div>

            <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2 scrollbar-hide">
              {tasks.length === 0 ? (
                <div className="text-center py-12 text-zinc-500 border border-dashed border-white/5 rounded-[2rem]">
                  No scheduled agents found. Create one on the left.
                </div>
              ) : (
                tasks.map((task) => (
                  <div 
                    key={task.id}
                    className={cn(
                      "p-5 rounded-[1.5rem] border transition-all text-sm flex flex-col justify-between gap-4",
                      task.enabled 
                        ? "bg-white/[0.01] border-white/5 hover:border-white/10" 
                        : "bg-white/[0.005] border-white/5 opacity-50"
                    )}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2.5">
                          <span className="font-bold text-white text-base">{task.name}</span>
                          <span className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded font-mono">
                            {task.cron_expression}
                          </span>
                        </div>
                        <p className="text-xs text-zinc-400 font-mono leading-relaxed bg-zinc-950/60 p-2.5 rounded-xl border border-white/5 italic">
                          "{task.agent_prompt}"
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Toggle Active Status */}
                        <button
                          onClick={() => handleToggleTask(task)}
                          className={cn(
                            "px-2.5 py-1.5 rounded-lg border text-[10px] font-bold tracking-wider transition-colors",
                            task.enabled 
                              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20"
                              : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700"
                          )}
                        >
                          {task.enabled ? "ACTIVE" : "PAUSED"}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-white/5 pt-4">
                      {/* Schedule Timestamps */}
                      <div className="flex flex-wrap gap-x-6 gap-y-2 text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">
                        <div className="flex items-center gap-1">
                          <span className="text-zinc-600">Last Run:</span>
                          <span className="text-zinc-400 font-mono">
                            {task.last_run ? new Date(task.last_run).toLocaleString() : "Never"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-zinc-600">Next Run:</span>
                          <span className="text-zinc-400 font-mono">
                            {task.next_run ? new Date(task.next_run).toLocaleString() : "N/A (Paused)"}
                          </span>
                        </div>
                      </div>

                      {/* Manual Trigger & Delete */}
                      <div className="flex items-center gap-2 self-end sm:self-auto">
                        <button
                          onClick={() => handleTriggerTask(task.id)}
                          title="Trigger execution now"
                          className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-lg text-xs hover:scale-105 active:scale-95 transition-all flex items-center gap-1.5"
                        >
                          <Play size={12} fill="currentColor" />
                          Run Now
                        </button>

                        <button 
                          onClick={() => handleDeleteTask(task.id)}
                          className="p-2 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 rounded-lg text-zinc-500 hover:text-red-400 transition-all"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
