"use client";

import React, { useEffect, useState } from "react";
import { 
  Database, 
  Trash2, 
  Search, 
  Calendar, 
  Cpu, 
  TrendingUp, 
  TrendingDown, 
  ChevronRight, 
  ChevronDown, 
  RefreshCw,
  Clock,
  Layers,
  Sparkles,
  CheckCircle2,
  XCircle,
  FolderDot
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, Project, EpisodicMemoryItem } from "@/lib/api";

export const MemoryBrowser = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState("default");
  const [episodes, setEpisodes] = useState<EpisodicMemoryItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedEpisode, setExpandedEpisode] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  // Fetch projects list
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const data = await api.getProjects();
        setProjects(data);
      } catch (err) {
        console.error("Failed to fetch projects for Memory Browser", err);
      }
    };
    fetchProjects();
  }, []);

  // Fetch memory episodes based on filters
  const fetchEpisodes = async () => {
    setIsLoading(true);
    try {
      const response = await api.getMemoryEpisodes(selectedProject, limit, offset);
      setEpisodes(response.episodes);
      setTotalCount(response.total);
    } catch (err) {
      console.error("Failed to load memory episodes", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchEpisodes();
  }, [selectedProject, offset]);

  // Handle deletion of a memory
  const handleDelete = async (id: string) => {
    setIsDeleting(id);
    try {
      await api.deleteMemoryEpisode(id);
      await fetchEpisodes();
      if (expandedEpisode === id) {
        setExpandedEpisode(null);
      }
    } catch (err) {
      console.error("Failed to delete episodic memory", err);
    } finally {
      setIsDeleting(null);
    }
  };

  // Local filter for search query
  const filteredEpisodes = episodes.filter(ep => {
    const query = searchQuery.toLowerCase();
    return (
      ep.task.toLowerCase().includes(query) ||
      ep.summary.toLowerCase().includes(query) ||
      ep.tools_used.some(tool => tool.toLowerCase().includes(query))
    );
  });

  // Calculate statistics from the currently fetched list
  const successCount = episodes.filter(ep => ep.success).length;
  const successRate = episodes.length > 0 ? Math.round((successCount / episodes.length) * 100) : 0;
  
  // Find the most frequent tool used
  const toolCounts: Record<string, number> = {};
  episodes.forEach(ep => {
    ep.tools_used.forEach(tool => {
      toolCounts[tool] = (toolCounts[tool] || 0) + 1;
    });
  });
  const topTool = Object.entries(toolCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "None";

  // Pagination helpers
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(totalCount / limit) || 1;

  const handlePrevPage = () => {
    if (offset >= limit) {
      setOffset(prev => prev - limit);
    }
  };

  const handleNextPage = () => {
    if (offset + limit < totalCount) {
      setOffset(prev => prev + limit);
    }
  };

  return (
    <div className="h-full w-full overflow-y-auto bg-[#09090b] p-8 lg:p-12 space-y-10">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 text-emerald-500"
          >
            <Sparkles size={16} />
            <span className="text-[10px] font-black uppercase tracking-[0.3em]">ASTRA Cognitive Storage</span>
          </motion.div>
          <motion.h1 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="text-4xl lg:text-5xl font-black text-white tracking-tight italic uppercase"
          >
            Memory <span className="text-zinc-500 not-italic font-light">Browser</span>
          </motion.h1>
        </div>

        {/* Workspace/Project Selector */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 }}
          className="flex items-center gap-3 bg-white/[0.02] border border-white/5 p-2 rounded-2xl"
        >
          <FolderDot size={18} className="text-zinc-500 ml-2" />
          <select 
            value={selectedProject}
            onChange={(e) => {
              setSelectedProject(e.target.value);
              setOffset(0); // Reset page on project change
            }}
            className="bg-transparent border-0 text-sm font-semibold text-white focus:ring-0 cursor-pointer pr-10 pl-1 uppercase tracking-wider"
          >
            <option value="default" className="bg-[#09090b] text-white">Default Workspace</option>
            {projects.map(proj => (
              <option key={proj.id} value={proj.id} className="bg-[#09090b] text-white">
                {proj.name}
              </option>
            ))}
          </select>
        </motion.div>
      </header>

      {/* Stats Cards Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass p-6 rounded-[2rem] border border-white/5 space-y-3 group hover:border-white/10 transition-all"
        >
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 text-emerald-400">
            <Database size={22} />
          </div>
          <div>
            <h3 className="text-3xl font-black text-white tracking-tight">{totalCount}</h3>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Total Persistent Episodes</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass p-6 rounded-[2rem] border border-white/5 space-y-3 group hover:border-white/10 transition-all"
        >
          <div className={cn(
            "w-12 h-12 rounded-2xl flex items-center justify-center border text-emerald-400",
            successRate >= 70 
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
              : "bg-amber-500/10 border-amber-500/20 text-amber-400"
          )}>
            {successRate >= 50 ? <TrendingUp size={22} /> : <TrendingDown size={22} />}
          </div>
          <div>
            <h3 className="text-3xl font-black text-white tracking-tight">{successRate}%</h3>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Task Success Rate</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="glass p-6 rounded-[2rem] border border-white/5 space-y-3 group hover:border-white/10 transition-all"
        >
          <div className="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center border border-blue-500/20 text-blue-400">
            <Cpu size={22} />
          </div>
          <div>
            <h3 className="text-xl font-black text-white truncate max-w-full tracking-tight uppercase italic">{topTool}</h3>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mt-1">Most Utilized Tool</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="glass p-6 rounded-[2rem] border border-white/5 space-y-3 group hover:border-white/10 transition-all"
        >
          <div className="w-12 h-12 rounded-2xl bg-purple-500/10 flex items-center justify-center border border-purple-500/20 text-purple-400">
            <Layers size={22} />
          </div>
          <div>
            <h3 className="text-3xl font-black text-white tracking-tight">SQLite</h3>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Cognitive Schema Engine</p>
          </div>
        </motion.div>
      </div>

      {/* Main List Section */}
      <div className="space-y-6">
        {/* Search & Actions Bar */}
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="w-full sm:flex-1 relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-500" size={18} />
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search cognitive records by task, summary, or tools..."
              className="w-full bg-white/[0.02] border border-white/5 rounded-2xl py-4 pl-12 pr-6 text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 transition-all font-medium text-sm"
            />
          </div>
          <button 
            onClick={fetchEpisodes}
            disabled={isLoading}
            className="w-full sm:w-auto px-6 py-4 rounded-2xl bg-white/[0.02] border border-white/5 text-white hover:bg-white/5 transition-all active:scale-95 flex items-center justify-center gap-2 text-sm font-semibold tracking-tight cursor-pointer"
          >
            <RefreshCw size={16} className={cn("text-zinc-400", isLoading && "animate-spin")} />
            Sync Storage
          </button>
        </div>

        {/* List of episodes */}
        <div className="space-y-4">
          {isLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-24 glass rounded-[1.5rem] border border-white/5 animate-pulse" />
              ))}
            </div>
          ) : filteredEpisodes.length === 0 ? (
            <div className="glass p-16 rounded-[2rem] border border-white/5 text-center space-y-4">
              <Database className="mx-auto text-zinc-600 w-12 h-12 opacity-60" />
              <div className="space-y-1">
                <h4 className="text-white font-bold text-lg uppercase tracking-tight">No Cognitive Episodes found</h4>
                <p className="text-zinc-500 text-sm max-w-md mx-auto">
                  ASTRA OS records episodes here when tasks complete in this workspace context. Try running a prompt first!
                </p>
              </div>
            </div>
          ) : (
            filteredEpisodes.map((ep) => {
              const isExpanded = expandedEpisode === ep.id;
              const formattedDate = new Date(ep.created_at).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short"
              });

              return (
                <motion.div
                  key={ep.id}
                  layout="position"
                  className={cn(
                    "glass rounded-[1.5rem] border transition-all overflow-hidden relative group",
                    isExpanded ? "border-white/15 bg-white/[0.03]" : "border-white/5 hover:border-white/10"
                  )}
                >
                  {/* Glass highlight bar */}
                  <div className={cn(
                    "absolute top-0 left-0 w-1.5 h-full transition-colors",
                    ep.success ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]" : "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.3)]"
                  )} />

                  {/* Header Row */}
                  <div 
                    onClick={() => setExpandedEpisode(isExpanded ? null : ep.id)}
                    className="p-6 pl-8 flex items-center justify-between gap-4 cursor-pointer select-none"
                  >
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        {/* Status Badge */}
                        <span className={cn(
                          "px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest flex items-center gap-1 border",
                          ep.success 
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" 
                            : "bg-red-500/10 text-red-400 border-red-500/20"
                        )}>
                          {ep.success ? (
                            <>
                              <CheckCircle2 size={10} />
                              Succeeded
                            </>
                          ) : (
                            <>
                              <XCircle size={10} />
                              Failed
                            </>
                          )}
                        </span>
                        
                        {/* Timestamp */}
                        <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider flex items-center gap-1.5">
                          <Calendar size={12} className="text-zinc-600" />
                          {formattedDate}
                        </span>

                        {/* ACCESS count indicator if relevant */}
                        {ep.access_count > 0 && (
                          <span className="text-[9px] text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider flex items-center gap-1">
                            <Clock size={10} />
                            Recalled {ep.access_count}x
                          </span>
                        )}
                      </div>

                      <h4 className="text-sm font-bold text-white tracking-tight uppercase truncate">
                        {ep.task}
                      </h4>
                    </div>

                    <div className="flex items-center gap-4">
                      {/* Tools summary chips (limit 3) */}
                      <div className="hidden lg:flex items-center gap-1.5">
                        {ep.tools_used.slice(0, 3).map((tool, idx) => (
                          <span 
                            key={idx} 
                            className="bg-white/[0.03] border border-white/5 text-[9px] text-zinc-400 font-bold px-2 py-0.5 rounded-md uppercase tracking-wider"
                          >
                            {tool}
                          </span>
                        ))}
                        {ep.tools_used.length > 3 && (
                          <span className="text-[9px] text-zinc-500 font-bold">
                            +{ep.tools_used.length - 3}
                          </span>
                        )}
                      </div>

                      {/* Expand Chevron */}
                      <div className="text-zinc-500 group-hover:text-white transition-colors">
                        {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Body Panel */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.3, ease: "easeInOut" }}
                        className="border-t border-white/5 bg-black/40 overflow-hidden"
                      >
                        <div className="p-8 pl-8 space-y-6">
                          {/* Summary text area */}
                          <div className="space-y-2.5">
                            <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Execution Summary</h5>
                            <p className="text-sm text-zinc-300 font-medium leading-relaxed bg-[#0c0c0e] border border-white/5 p-4 rounded-xl">
                              {ep.summary || "No execution summary provided by the cognitive engine."}
                            </p>
                          </div>

                          {/* Detail Grid */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                            {/* Tools Used Box */}
                            <div className="space-y-2.5">
                              <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-1.5">
                                <Cpu size={12} className="text-zinc-600" />
                                Interactive Neural Tools
                              </h5>
                              <div className="flex flex-wrap gap-2">
                                {ep.tools_used.length === 0 ? (
                                  <span className="text-xs text-zinc-600 italic">No tools utilized in this task.</span>
                                ) : (
                                  ep.tools_used.map((tool, idx) => (
                                    <span 
                                      key={idx} 
                                      className="bg-white/5 border border-white/5 text-xs text-white font-semibold px-3 py-1 rounded-xl uppercase tracking-wider"
                                    >
                                      {tool}
                                    </span>
                                  ))
                                )}
                              </div>
                            </div>

                            {/* Additional metadata box */}
                            <div className="space-y-2.5">
                              <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Metadata Context</h5>
                              <div className="space-y-1 text-xs text-zinc-400 font-medium">
                                <div><span className="text-zinc-600 font-bold uppercase tracking-wider text-[10px]">Episode UUID:</span> {ep.id}</div>
                                {ep.session_id && <div><span className="text-zinc-600 font-bold uppercase tracking-wider text-[10px]">Session Key:</span> {ep.session_id}</div>}
                                {ep.last_accessed && (
                                  <div>
                                    <span className="text-zinc-600 font-bold uppercase tracking-wider text-[10px]">Last Recalled:</span>{" "}
                                    {new Date(ep.last_accessed).toLocaleString()}
                                  </div>
                                )}
                                <div><span className="text-zinc-600 font-bold uppercase tracking-wider text-[10px]">Importance score:</span> {ep.importance || 1} / 5</div>
                              </div>
                            </div>
                          </div>

                          {/* Delete Episode Action */}
                          <div className="flex justify-end pt-4 border-t border-white/5">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                if (confirm("Are you absolutely sure you want to permanently erase this cognitive memory record from SQLite persistence? This cannot be undone.")) {
                                  handleDelete(ep.id);
                                }
                              }}
                              disabled={isDeleting === ep.id}
                              className="px-5 py-3 bg-red-500/10 hover:bg-red-500 text-red-400 hover:text-white border border-red-500/20 hover:border-transparent rounded-xl transition-all duration-300 flex items-center gap-2 text-xs font-bold uppercase tracking-wider disabled:opacity-50 cursor-pointer"
                            >
                              <Trash2 size={14} />
                              {isDeleting === ep.id ? "Erase in progress..." : "Erase memory record"}
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })
          )}
        </div>

        {/* Pagination controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-white/5 pt-6">
            <span className="text-xs text-zinc-500 font-semibold tracking-tight uppercase">
              Page {currentPage} of {totalPages} • ({totalCount} items)
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={handlePrevPage}
                disabled={offset === 0}
                className="px-5 py-3 rounded-xl bg-white/[0.02] border border-white/5 text-white hover:bg-white/5 transition-all text-xs font-bold uppercase tracking-wider disabled:opacity-30 cursor-pointer"
              >
                Previous
              </button>
              <button
                onClick={handleNextPage}
                disabled={offset + limit >= totalCount}
                className="px-5 py-3 rounded-xl bg-white/[0.02] border border-white/5 text-white hover:bg-white/5 transition-all text-xs font-bold uppercase tracking-wider disabled:opacity-30 cursor-pointer"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
