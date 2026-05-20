"use client";

import React, { useEffect, useState } from "react";
import { 
  BarChart3, 
  Clock, 
  Database, 
  FileText, 
  Plus, 
  Sparkles, 
  Zap, 
  ArrowRight,
  Activity,
  ShieldCheck,
  Cpu
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, Project } from "@/lib/api";
import { WorkflowEngine } from "@/components/WorkflowEngine";

interface DashboardProps {
  onSelectProject: (id: string, label?: string) => void;
}

export const Dashboard = ({ onSelectProject }: DashboardProps) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [liveStats, setLiveStats] = useState({
    documents_indexed: 0,
    episodic_memories: 0,
    ollama_status: "disconnected",
    model_name: "none",
    ram_usage_percent: 0,
    cpu_percent: 0,
  });

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

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const s = await api.getStats();
        setLiveStats(s);
      } catch (err) {
        console.error("Failed to fetch dashboard stats:", err);
      }
    };
    
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const stats = [
    { 
      label: "Neural Engine", 
      value: liveStats.ollama_status === "connected" ? "Active" : "Offline", 
      sub: liveStats.model_name, 
      icon: Cpu, 
      color: liveStats.ollama_status === "connected" ? "text-emerald-500" : "text-red-500" 
    },
    { 
      label: "Knowledge Assets", 
      value: String(liveStats.documents_indexed), 
      sub: `${liveStats.episodic_memories} Memories`, 
      icon: Database, 
      color: "text-blue-500" 
    },
    { 
      label: "System CPU Load", 
      value: `${liveStats.cpu_percent.toFixed(1)}%`, 
      sub: "Processor Load", 
      icon: Activity, 
      color: "text-amber-500" 
    },
    { 
      label: "Memory Usage", 
      value: `${liveStats.ram_usage_percent.toFixed(1)}%`, 
      sub: "RAM Allocated", 
      icon: ShieldCheck, 
      color: "text-purple-500" 
    },
  ];

  return (
    <div className="h-full w-full overflow-y-auto bg-[#09090b] p-8 lg:p-12 space-y-12">
      {/* Welcome Header */}
      <header className="space-y-2">
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 text-emerald-500"
        >
          <Sparkles size={16} />
          <span className="text-[10px] font-black uppercase tracking-[0.3em]">System Overview</span>
        </motion.div>
        <motion.h1 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-4xl lg:text-5xl font-black text-white tracking-tight italic uppercase"
        >
          Astra <span className="text-zinc-500 not-italic font-light">OS</span>
        </motion.h1>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1 }}
            className="glass p-6 rounded-[2rem] border border-white/5 space-y-4 group hover:border-white/10 transition-all"
          >
            <div className={cn("w-12 h-12 rounded-2xl bg-white/[0.03] flex items-center justify-center border border-white/5", stat.color)}>
              <stat.icon size={24} />
            </div>
            <div>
              <h3 className="text-2xl font-bold text-white">{stat.value}</h3>
              <p className="text-xs font-bold text-zinc-500 uppercase tracking-widest">{stat.label}</p>
              <p className="text-[10px] text-zinc-600 mt-1">{stat.sub}</p>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Recent Projects */}
        <section className="lg:col-span-2 space-y-12">
          {/* Workflow Integration */}
          <WorkflowEngine />
          
          <div className="space-y-6">
            <h2 className="text-sm font-black text-zinc-400 uppercase tracking-[0.2em] flex items-center gap-2 pt-4 border-t border-white/5">
              <Clock size={16} />
              Recent Workspaces
            </h2>
            
            <div className="space-y-4">
            {isLoading ? (
              <div className="h-40 glass rounded-[2rem] animate-pulse" />
            ) : projects.slice(0, 4).map((proj, i) => (
              <motion.div
                key={proj.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.1 }}
                onClick={() => onSelectProject(proj.id, proj.name)}
                className="group glass p-5 rounded-[1.5rem] border border-white/5 flex items-center justify-between hover:border-white/20 transition-all cursor-pointer hover:translate-x-1"
              >
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center font-bold text-xl transition-all",
                    proj.project_type === "research" ? "bg-purple-500/10 text-purple-400 border border-purple-500/20" : 
                    proj.project_type === "code" ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : 
                    "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  )}>
                    {proj.name[0].toUpperCase()}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors uppercase tracking-tight">{proj.name}</h4>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">{proj.project_type} • {new Date(proj.last_accessed_at).toLocaleDateString()}</p>
                  </div>
                </div>
                <ArrowRight size={18} className="text-zinc-600 group-hover:text-white transition-all transform group-hover:translate-x-1" />
              </motion.div>
            ))}
            
            {!isLoading && projects.length === 0 && (
              <div className="p-12 glass rounded-[2rem] border border-dashed border-white/10 text-center space-y-4">
                <p className="text-zinc-500 font-medium">No active contexts found. Start by creating a new workspace.</p>
                <button className="px-6 py-2 rounded-xl bg-white/5 border border-white/10 text-white text-xs font-bold uppercase tracking-widest hover:bg-white/10 transition-all">
                  Initialize First Context
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

        {/* Neural Activity / Sidebar info */}
        <section className="space-y-6">
          <h2 className="text-sm font-black text-zinc-400 uppercase tracking-[0.2em] flex items-center gap-2">
            <BarChart3 size={16} />
            Context Density
          </h2>
          <div className="glass p-8 rounded-[2rem] border border-white/5 aspect-square flex flex-col justify-between overflow-hidden relative group">
             <div className="space-y-4 z-10">
                <div className="space-y-1">
                   <div className="flex justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      <span>RAG Accuracy</span>
                      <span>98%</span>
                   </div>
                   <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <motion.div initial={{ width: 0 }} animate={{ width: "98%" }} transition={{ duration: 1.5 }} className="h-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                   </div>
                </div>
                <div className="space-y-1">
                   <div className="flex justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      <span>Agent Latency</span>
                      <span>42ms</span>
                   </div>
                   <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <motion.div initial={{ width: 0 }} animate={{ width: "20%" }} transition={{ duration: 1.5, delay: 0.2 }} className="h-full bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
                   </div>
                </div>
             </div>
             
             <div className="group-hover:scale-110 transition-transform duration-700">
                <Zap className="text-zinc-800/20 w-32 h-32 absolute -bottom-4 -right-4" />
                <div className="space-y-1">
                   <p className="text-5xl font-black text-white italic tracking-tighter">X-10</p>
                   <p className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.4em]">Neural Bandwidth</p>
                </div>
             </div>
          </div>
        </section>
      </div>
    </div>
  );
};
