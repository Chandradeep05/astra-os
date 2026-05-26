"use client";

import React, { useEffect, useState } from "react";
import { Plus, LayoutGrid, MessageSquare, Settings, Database, Code, Globe, User, Loader2, X, Cpu, FileText, Activity, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { api, Project } from "@/lib/api";
import { useAstraRuntime } from "@/hooks/useAstraRuntime";

interface SidebarProps {
  activeProject: string;
  onSelectProject: (id: string, label?: string) => void;
}

export const Sidebar = ({ activeProject, onSelectProject }: SidebarProps) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const { taskRunsUnreadCount, markTasksViewed } = useAstraRuntime();

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

  const navItems = [
    { icon: LayoutGrid, label: "Dashboard", id: "dashboard" },
    { icon: Cpu, label: "Autonomous Agent", id: "agent" },
    { icon: MessageSquare, label: "Main Chat", id: "default" },
    { icon: FileText, label: "Document Manager", id: "documents" },
    { icon: Database, label: "Memory Browser", id: "memory-browser" },
    { icon: Activity, label: "Execution Engine", id: "tasks" },
    { icon: Calendar, label: "Scheduled Agents", id: "scheduled-tasks" },
  ];

  return (
    <>
      <aside className="w-64 h-full glass border-r border-white/5 flex flex-col z-50">
        {/* Header / Brand */}
        <div className="p-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-white text-black flex items-center justify-center border border-white/20 shadow-[0_0_15px_rgba(255,255,255,0.2)]">
            <span className="text-sm font-bold">A</span>
          </div>
          <span className="text-lg font-bold tracking-tight text-white uppercase italic">ASTRA OS</span>
        </div>

        {/* New Project Button */}
        <div className="px-4 mb-8">
          <button 
            onClick={() => setIsModalOpen(true)}
            className="w-full py-2.5 rounded-xl bg-white text-black font-semibold flex items-center justify-center gap-2 hover:bg-zinc-200 transition-all active:scale-95 shadow-[0_0_20px_rgba(255,255,255,0.1)]"
          >
            <Plus size={18} />
            New Context
          </button>
        </div>

        {/* Primary Navigation */}
        <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto">
          <div className="px-3 mb-2">
            <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Main</span>
          </div>
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onSelectProject(item.id, item.label);
                // Clear unread badge when Execution Engine is opened
                if (item.id === "tasks") markTasksViewed();
              }}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 group relative",
                activeProject === item.id 
                  ? "bg-white/10 text-white border border-white/5 shadow-inner" 
                  : "text-zinc-500 hover:bg-white/[0.03] hover:text-white"
              )}
            >
              {activeProject === item.id && (
                <motion.div 
                  layoutId="active-pill"
                  className="absolute left-0 w-1 h-4 bg-white rounded-full ml-1"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <item.icon size={18} className={cn(
                "transition-colors duration-300",
                activeProject === item.id ? "text-white" : "text-zinc-500 group-hover:text-zinc-300"
              )} />
              <span className="text-sm font-semibold tracking-tight">{item.label}</span>
              {/* Unread badge for Execution Engine */}
              {item.id === "tasks" && taskRunsUnreadCount > 0 && (
                <span className="ml-auto flex items-center gap-1.5">
                  <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-500/20 border border-emerald-500/30 text-[10px] font-bold text-emerald-400 flex items-center justify-center">
                    {taskRunsUnreadCount > 99 ? "99+" : taskRunsUnreadCount}
                  </span>
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
                </span>
              )}
            </button>
          ))}

          <div className="px-3 mt-6 mb-2">
            <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest text-[8px]">Projects / Contexts</span>
          </div>
          
          {isLoading ? (
            <div className="flex justify-center p-4">
              <Loader2 size={16} className="animate-spin text-zinc-600" />
            </div>
          ) : (
            projects.map((proj) => (
              <button
                key={proj.id}
                onClick={() => onSelectProject(proj.id, proj.name)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 group relative",
                  activeProject === proj.id 
                    ? "bg-white/10 text-white border border-white/5 shadow-inner" 
                    : "text-zinc-500 hover:bg-white/[0.03] hover:text-white"
                )}
              >
                {activeProject === proj.id && (
                  <motion.div 
                    layoutId="active-pill"
                    className="absolute left-0 w-1 h-4 bg-white rounded-full ml-1"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
                <div className={cn(
                  "w-2 h-2 rounded-full",
                  proj.project_type === "research" ? "bg-purple-500" : 
                  proj.project_type === "code" ? "bg-blue-500" : "bg-emerald-500"
                )} />
                <span className="text-sm font-semibold tracking-tight truncate">{proj.name}</span>
              </button>
            ))
          )}
        </nav>

        {/* Bottom Profile / Settings */}
        <div className="p-4 border-t border-white/5 space-y-1.5 bg-black/20">
          <button 
            onClick={() => onSelectProject("settings", "System Settings")}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all group",
              activeProject === "settings" ? "bg-white/10 text-white" : "text-zinc-500 hover:bg-white/5 hover:text-white"
            )}
          >
            <Settings size={18} className={cn("transition-transform duration-500", activeProject === "settings" ? "rotate-45 text-white" : "group-hover:rotate-45 text-zinc-500 group-hover:text-white")} />
            <span className="text-xs font-bold uppercase tracking-wider">System Settings</span>
          </button>
          <button className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-white/[0.02] border border-white/5 hover:bg-white/5 transition-all group cursor-pointer">
            <div className="flex items-center gap-3">
               <div className="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-[10px] text-emerald-400 font-bold">JD</div>
               <span className="text-xs font-bold text-white uppercase tracking-tight">Founder Mode</span>
            </div>
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
          </button>
        </div>
      </aside>

      {/* New Project Modal */}
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
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="relative w-full max-w-md glass border border-white/10 rounded-[2rem] p-8 shadow-2xl overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-500 to-blue-500" />
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-white">Create New Context</h3>
                <button onClick={() => setIsModalOpen(false)} className="p-2 hover:bg-white/5 rounded-full text-zinc-400 hover:text-white transition-colors">
                  <X size={20} />
                </button>
              </div>
              
              <form onSubmit={handleCreateProject} className="space-y-6">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Workspace Name</label>
                  <input 
                    autoFocus
                    type="text"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    placeholder="e.g., Marketing Strategy"
                    className="w-full bg-white/5 border border-white/5 rounded-2xl px-5 py-4 text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/20 transition-all font-medium"
                  />
                </div>
                
                <button 
                  type="submit"
                  disabled={isCreating || !newProjectName.trim()}
                  className="w-full py-4 rounded-[1.5rem] bg-white text-black font-bold flex items-center justify-center gap-2 hover:bg-zinc-200 transition-all disabled:opacity-50"
                >
                  {isCreating ? <Loader2 size={20} className="animate-spin" /> : "INITIALIZE CONTEXT"}
                </button>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};
