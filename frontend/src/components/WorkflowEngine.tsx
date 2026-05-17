"use client";

import React, { useState, useEffect } from "react";
import { 
  Plus, 
  Zap, 
  Play, 
  Pause, 
  Trash2, 
  Clock, 
  Settings2, 
  Activity, 
  ChevronRight,
  Loader2,
  AlertCircle
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, Workflow } from "@/lib/api";

interface WorkflowEngineProps {
  project_id?: string;
}

export const WorkflowEngine = ({ project_id }: WorkflowEngineProps) => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [newWorkflowName, setNewWorkflowName] = useState("");
  const [steps, setSteps] = useState<string[]>([]);
  const [currentStepText, setCurrentStepText] = useState("");

  const fetchData = async () => {
    try {
      const data = await api.getWorkflows(project_id);
      setWorkflows(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [project_id]);

  const handleCreate = async () => {
    if (!newWorkflowName.trim()) return;
    setIsCreating(true);
    try {
      await api.createWorkflow({
        name: newWorkflowName,
        project_id: project_id || "default",
        type: "automation",
        trigger_type: "manual",
        steps: steps.length > 0 ? steps : [newWorkflowName]
      });
      setNewWorkflowName("");
      setSteps([]);
      fetchData();
    } catch (err) {
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleTrigger = async (id: string) => {
    try {
      await api.triggerWorkflow(id);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white uppercase tracking-tighter flex items-center gap-3">
            <Zap className="text-amber-500 fill-amber-500/20" size={24} />
            Automation Engine
          </h2>
          <p className="text-xs text-zinc-500 font-bold uppercase tracking-widest mt-1">
            Agentic Workflows & Transformation Tasks
          </p>
        </div>
        
        <div className="flex bg-white/5 rounded-2xl p-1 border border-white/5">
           <input 
             type="text" 
             value={newWorkflowName}
             onChange={(e) => setNewWorkflowName(e.target.value)}
             placeholder="New Task Name..." 
             className="bg-transparent border-none focus:ring-0 text-sm text-white px-4 py-2 w-48 placeholder:text-zinc-600"
           />
           <button 
             onClick={handleCreate}
             disabled={isCreating || !newWorkflowName.trim()}
             className="bg-white text-black rounded-xl px-4 py-2 text-xs font-bold uppercase tracking-widest hover:bg-zinc-200 transition-all disabled:opacity-50"
           >
             {isCreating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
           </button>
        </div>
      </div>

      {/* Logic Block Builder - Visual Step Sequence */}
      <AnimatePresence>
        {newWorkflowName.trim() && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-white/5 rounded-[2rem] border border-white/5 p-6 space-y-4"
          >
            <div className="flex items-center justify-between border-b border-white/5 pb-4 mb-4">
              <span className="text-[10px] font-black uppercase text-zinc-500 tracking-widest">Logic Pipeline Design</span>
              <span className="text-[10px] font-black uppercase text-amber-500 tracking-widest">{steps.length} Active Directives</span>
            </div>

            <div className="space-y-3">
              {steps.map((step, idx) => (
                <motion.div 
                  key={idx} 
                  initial={{ x: -10, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  className="flex items-center gap-3 bg-white/5 p-3 rounded-xl border border-white/5"
                >
                  <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-[10px] font-bold text-white">
                    {idx + 1}
                  </div>
                  <span className="text-xs text-zinc-300 flex-1">{step}</span>
                  <button 
                    onClick={() => setSteps(steps.filter((_, i) => i !== idx))}
                    className="p-1 text-zinc-600 hover:text-red-500 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </motion.div>
              ))}
            </div>

            <div className="flex gap-2">
              <input 
                type="text"
                value={currentStepText}
                onChange={(e) => setCurrentStepText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && currentStepText.trim() && (setSteps([...steps, currentStepText]), setCurrentStepText(""))}
                placeholder="Add intelligence directive (e.g. 'Search for X' or 'Summarize docs')"
                className="bg-black/20 border border-white/5 rounded-xl px-4 py-3 text-xs text-white flex-1 focus:border-amber-500/50 outline-none transition-all placeholder:text-zinc-700"
              />
              <button 
                onClick={() => {
                  if (!currentStepText.trim()) return;
                  setSteps([...steps, currentStepText]);
                  setCurrentStepText("");
                }}
                className="p-3 bg-amber-500/10 text-amber-500 rounded-xl hover:bg-amber-500/20 border border-amber-500/20"
              >
                <Plus size={16} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 gap-4">
        {isLoading ? (
          <div className="flex justify-center p-12">
            <Loader2 className="animate-spin text-zinc-700" size={32} />
          </div>
        ) : workflows.length === 0 ? (
          <div className="p-12 glass rounded-[2rem] border border-dashed border-white/10 text-center space-y-4">
            <AlertCircle size={32} className="text-zinc-700 mx-auto" />
            <p className="text-zinc-500 font-medium tracking-tight">No active workflows found for this context.</p>
          </div>
        ) : (
          workflows.map((wf, i) => (
            <motion.div
              key={wf.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="group glass p-6 rounded-[2rem] border border-white/5 flex items-center justify-between hover:border-white/10 transition-all"
            >
              <div className="flex items-center gap-6">
                <div className={cn(
                  "w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-500",
                  wf.status === "active" ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 shadow-[0_0_20px_rgba(16,185,129,0.1)]" : "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20"
                )}>
                  <Activity size={28} className={cn(wf.status === "active" && "animate-pulse")} />
                </div>
                <div>
                  <h4 className="text-lg font-bold text-white tracking-tight uppercase group-hover:text-amber-500 transition-colors">{wf.name}</h4>
                  <div className="flex items-center gap-4 mt-1">
                    <span className="text-[10px] font-black text-emerald-500 uppercase tracking-widest flex items-center gap-1.5">
                      <Settings2 size={12} /> {wf.steps?.length || 0} Directives
                    </span>
                    <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-1.5">
                      <Clock size={12} /> {wf.last_run ? new Date(wf.last_run).toLocaleTimeString() : "Never Run"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button 
                  onClick={() => handleTrigger(wf.id)}
                  className="p-3 bg-white/5 hover:bg-white/10 rounded-xl text-zinc-400 hover:text-emerald-500 transition-all border border-white/5"
                  title="Run Once"
                >
                  <Play size={18} fill="currentColor" fillOpacity={0.1} />
                </button>
                <button className="p-3 bg-white/5 hover:bg-white/10 rounded-xl text-zinc-400 hover:text-white transition-all border border-white/5" title="Settings">
                  <Settings2 size={18} />
                </button>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
};
