"use client";

import React, { useEffect, useState } from "react";
import { 
  Settings, 
  Save, 
  Plus, 
  Trash2, 
  Loader2, 
  CheckCircle2, 
  AlertCircle,
  HelpCircle,
  ShieldAlert,
  Sliders,
  Cpu,
  UserCheck,
  Moon,
  Sun,
  FolderPlus,
  RefreshCw,
  Folder
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAstraRuntime } from "@/hooks/useAstraRuntime";

export const SettingsPanel = () => {
  const {
    sleepStatus,
    sleepEnabled,
    sleepTimeoutMinutes,
    triggerSleep,
    triggerWake,
    setSleepEnabled,
    setSleepTimeout,
  } = useAstraRuntime();

  const [settings, setSettings] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  // Input states for adding new rules
  const [newDoRule, setNewDoRule] = useState("");
  const [newDontRule, setNewDontRule] = useState("");

  // Watcher state
  const [watchedDirs, setWatchedDirs] = useState<any[]>([]);
  const [isWatcherLoading, setIsWatcherLoading] = useState(true);
  const [watcherPath, setWatcherPath] = useState("");
  const [watcherProject, setWatcherProject] = useState("default");
  const [watcherRecursive, setWatcherRecursive] = useState(false);
  const [watcherExtensions, setWatcherExtensions] = useState(".txt,.md,.pdf,.csv,.docx");
  const [watcherDebounce, setWatcherDebounce] = useState(2);
  const [projects, setProjects] = useState<any[]>([]);

  const fetchSettings = async () => {
    try {
      setIsLoading(true);
      const data = await api.getSettings();
      setSettings(data);
    } catch (err: any) {
      console.error(err);
      setErrorMessage("Failed to load settings from server.");
    } finally {
      setIsLoading(false);
    }
  };

  const fetchWatcherAndProjects = async () => {
    try {
      setIsWatcherLoading(true);
      const dirs = await api.listWatchedDirectories();
      setWatchedDirs(dirs);
      const projs = await api.getProjects();
      setProjects(projs);
    } catch (err) {
      console.error("Failed to load watcher dirs or projects:", err);
    } finally {
      setIsWatcherLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    fetchWatcherAndProjects();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveStatus("idle");
    try {
      await api.updateSettings(settings);
      setSaveStatus("success");
      setTimeout(() => setSaveStatus("idle"), 4000);
    } catch (err: any) {
      console.error(err);
      setSaveStatus("error");
      setErrorMessage(err.message || "Failed to save settings.");
    } finally {
      setIsSaving(false);
    }
  };

  const updateField = (section: string | null, field: string, value: any) => {
    setSettings((prev: any) => {
      if (section) {
        return {
          ...prev,
          [section]: {
            ...prev[section],
            [field]: value
          }
        };
      }
      return {
        ...prev,
        [field]: value
      };
    });
  };

  const handleAddDoRule = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDoRule.trim()) return;
    setSettings((prev: any) => ({
      ...prev,
      do_rules: [...(prev.do_rules || []), newDoRule.trim()]
    }));
    setNewDoRule("");
  };

  const handleAddDontRule = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDontRule.trim()) return;
    setSettings((prev: any) => ({
      ...prev,
      dont_rules: [...(prev.dont_rules || []), newDontRule.trim()]
    }));
    setNewDontRule("");
  };

  const handleRemoveDoRule = (index: number) => {
    setSettings((prev: any) => ({
      ...prev,
      do_rules: prev.do_rules.filter((_: any, i: number) => i !== index)
    }));
  };

  const handleRemoveDontRule = (index: number) => {
    setSettings((prev: any) => ({
      ...prev,
      dont_rules: prev.dont_rules.filter((_: any, i: number) => i !== index)
    }));
  };

  const handleAddWatcher = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!watcherPath.trim()) return;
    try {
      const newDir = await api.addWatchedDirectory({
        path: watcherPath.trim(),
        project_id: watcherProject,
        recursive: watcherRecursive,
        allowed_extensions: watcherExtensions.trim(),
        debounce_seconds: Number(watcherDebounce) || 2,
        enabled: true,
      });
      setWatchedDirs((prev) => [...prev, newDir]);
      setWatcherPath("");
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Failed to add watched directory");
    }
  };

  const handleDeleteWatcher = async (id: number) => {
    try {
      await api.deleteWatchedDirectory(id);
      setWatchedDirs((prev) => prev.filter((d) => d.id !== id));
    } catch (err: any) {
      console.error(err);
      alert("Failed to delete watched directory");
    }
  };

  const handleToggleWatcher = async (dir: any) => {
    try {
      const updated = await api.updateWatchedDirectory(dir.id, {
        enabled: !dir.enabled,
      });
      setWatchedDirs((prev) =>
        prev.map((d) => (d.id === dir.id ? { ...d, enabled: updated.enabled } : d))
      );
    } catch (err: any) {
      console.error(err);
      alert("Failed to toggle watched directory status");
    }
  };

  const handleScanWatcher = async (id: number) => {
    try {
      alert("Scan triggered. Files are being processed in the background.");
      await api.triggerWatchedDirectoryScan(id);
      fetchWatcherAndProjects();
    } catch (err: any) {
      console.error(err);
      alert("Failed to trigger scan");
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <Loader2 className="animate-spin text-zinc-600" size={32} />
        <span className="text-sm text-zinc-500 font-medium">Loading system settings...</span>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center gap-4">
        <AlertCircle className="text-red-500" size={40} />
        <p className="text-white font-bold">Failed to load system config</p>
        <p className="text-sm text-zinc-500">{errorMessage}</p>
        <button onClick={fetchSettings} className="px-6 py-2.5 rounded-xl bg-white text-black font-bold">Try Again</button>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto bg-[#09090b] p-8 lg:p-12 space-y-12 pb-24">
      
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-emerald-500">
            <Sliders size={16} />
            <span className="text-[10px] font-black uppercase tracking-[0.3em]">System Personalization</span>
          </div>
          <h1 className="text-4xl font-black text-white tracking-tight italic uppercase">
            System <span className="text-zinc-500 not-italic font-light">Settings</span>
          </h1>
          <p className="text-zinc-400 text-sm max-w-2xl">
            Configure agent personality, behavior rules, constraints, and tool execution permissions. Saving invalidates prompt cache immediately.
          </p>
        </div>

        {/* Save button */}
        <div className="flex items-center gap-4">
          <AnimatePresence>
            {saveStatus === "success" && (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-2 text-emerald-400 text-sm font-semibold bg-emerald-500/10 border border-emerald-500/20 px-4 py-2 rounded-xl"
              >
                <CheckCircle2 size={16} />
                <span>Configuration Saved</span>
              </motion.div>
            )}
            {saveStatus === "error" && (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-2 text-red-400 text-sm font-semibold bg-red-500/10 border border-red-500/20 px-4 py-2 rounded-xl"
              >
                <AlertCircle size={16} />
                <span>{errorMessage || "Save Failed"}</span>
              </motion.div>
            )}
          </AnimatePresence>

          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-6 py-3 rounded-2xl bg-white hover:bg-zinc-200 text-black font-bold flex items-center gap-2 transition-all active:scale-95 disabled:opacity-50"
          >
            {isSaving ? (
              <Loader2 className="animate-spin" size={18} />
            ) : (
              <Save size={18} />
            )}
            SAVE CHANGES
          </button>
        </div>
      </header>

      {/* Main Settings Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Left Column: General & Constraints & Security */}
        <div className="space-y-8 xl:col-span-1">
          
          {/* Sleep Mode Card */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                {sleepStatus.sleeping ? (
                  <Moon size={16} className="text-amber-500 animate-pulse" />
                ) : (
                  <Sun size={16} className="text-emerald-500" />
                )}
                Sleep Mode
              </h3>
              <span className={cn(
                "text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border",
                sleepStatus.sleeping 
                  ? "bg-amber-500/10 border-amber-500/20 text-amber-400" 
                  : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              )}>
                {sleepStatus.sleeping ? "Sleeping" : "Awake"}
              </span>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-xs font-semibold text-zinc-200">Auto-Sleep</label>
                  <span className="text-[10px] text-zinc-500">Unload model when inactive</span>
                </div>
                <button
                  onClick={() => setSleepEnabled(!sleepEnabled)}
                  className={cn(
                    "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                    sleepEnabled ? "bg-emerald-600" : "bg-zinc-800"
                  )}
                >
                  <span
                    className={cn(
                      "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
                      sleepEnabled ? "translate-x-6" : "translate-x-1"
                    )}
                  />
                </button>
              </div>

              {sleepEnabled && (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Idle Timeout</label>
                    <span className="text-xs font-semibold text-zinc-300">{sleepTimeoutMinutes} min</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="30"
                    step="5"
                    value={sleepTimeoutMinutes}
                    onChange={(e) => setSleepTimeout(parseInt(e.target.value))}
                    className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 pt-2">
                <button
                  onClick={triggerSleep}
                  disabled={sleepStatus.sleeping}
                  className="px-4 py-2.5 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 text-white text-xs font-bold transition-all disabled:opacity-50"
                >
                  Sleep Now
                </button>
                <button
                  onClick={triggerWake}
                  disabled={!sleepStatus.sleeping}
                  className="px-4 py-2.5 rounded-xl bg-white hover:bg-zinc-200 text-black text-xs font-bold transition-all disabled:opacity-50"
                >
                  Wake Up
                </button>
              </div>
            </div>
          </div>

          {/* General Config Card */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
              <UserCheck size={16} className="text-emerald-500" />
              General Identity
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Persona Name</label>
                <input 
                  type="text"
                  value={settings.persona_name || ""}
                  onChange={(e) => updateField(null, "persona_name", e.target.value)}
                  className="w-full bg-white/5 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10 font-semibold"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">System Tone</label>
                <select 
                  value={settings.tone || "professional"}
                  onChange={(e) => updateField(null, "tone", e.target.value)}
                  className="w-full bg-zinc-900 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white focus:ring-0 focus:border-white/10 font-semibold"
                >
                  <option value="professional">Professional</option>
                  <option value="friendly">Friendly / Conversational</option>
                  <option value="concise">Ultra-Concise</option>
                  <option value="creative">Creative / Exploratory</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Language</label>
                <input 
                  type="text"
                  value={settings.language || "en"}
                  onChange={(e) => updateField(null, "language", e.target.value)}
                  className="w-full bg-white/5 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white focus:ring-0 focus:border-white/10 font-semibold"
                />
              </div>
            </div>
          </div>

          {/* Output Constraints Card */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
              <Cpu size={16} className="text-blue-500" />
              Output Constraints
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Max Response Length</label>
                <select 
                  value={settings.output_constraints?.max_response_length || "medium"}
                  onChange={(e) => updateField("output_constraints", "max_response_length", e.target.value)}
                  className="w-full bg-zinc-900 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white focus:ring-0 focus:border-white/10 font-semibold"
                >
                  <option value="short">Short (under 150 words)</option>
                  <option value="medium">Medium (standard)</option>
                  <option value="long">Long (detailed breakdowns)</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Code Comment Style</label>
                <select 
                  value={settings.output_constraints?.code_style || "clean"}
                  onChange={(e) => updateField("output_constraints", "code_style", e.target.value)}
                  className="w-full bg-zinc-900 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white focus:ring-0 focus:border-white/10 font-semibold"
                >
                  <option value="clean with comments">Clean with line comments</option>
                  <option value="highly commented">Detailed docstrings and comments</option>
                  <option value="minimalist">Minimal comments (self-documenting)</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">List Bullet Style</label>
                <select 
                  value={settings.output_constraints?.list_style || "bullet"}
                  onChange={(e) => updateField("output_constraints", "list_style", e.target.value)}
                  className="w-full bg-zinc-900 border border-white/5 rounded-2xl px-4 py-3.5 text-sm text-white focus:ring-0 focus:border-white/10 font-semibold"
                >
                  <option value="bullet">Standard Bullets (-)</option>
                  <option value="numbered">Numbered Lists (1.)</option>
                  <option value="unicode">Unicode Glyphs (•)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Automation & Safety Permissions */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6 bg-red-500/[0.01]">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
              <ShieldAlert size={16} className="text-red-500 animate-pulse" />
              Tool Execution Gates
            </h3>
            
            <div className="space-y-4">
              {Object.keys(settings.automation_permissions || {}).map((toolKey) => (
                <div key={toolKey} className="flex items-center justify-between gap-4 py-2 border-b border-white/5 last:border-0">
                  <span className="text-xs font-semibold text-zinc-300 capitalize">{toolKey.replace("_", " ")}</span>
                  <select
                    value={settings.automation_permissions[toolKey]}
                    onChange={(e) => updateField("automation_permissions", toolKey, e.target.value)}
                    className="bg-zinc-950 border border-white/5 text-[11px] rounded-lg px-2.5 py-1.5 text-zinc-400 font-bold focus:ring-0 focus:border-white/10"
                  >
                    <option value="auto">Auto-Run (Implicit)</option>
                    <option value="always_confirm">Gate Approval</option>
                    <option value="block">Block Execution</option>
                  </select>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Right Columns: Rules Editor (Do / Don't) */}
        <div className="xl:col-span-2 space-y-8">
          
          {/* DO Rules */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <div className="flex items-center justify-between border-b border-white/5 pb-4">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <CheckCircle2 size={16} className="text-emerald-500" />
                Negative / Behavioral Constraints (Do Rules)
              </h3>
            </div>

            <form onSubmit={handleAddDoRule} className="flex gap-4">
              <input 
                type="text"
                value={newDoRule}
                onChange={(e) => setNewDoRule(e.target.value)}
                placeholder="Add rule (e.g., Output responses formatted in tabular form...)"
                className="flex-1 bg-white/5 border border-white/5 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10"
              />
              <button 
                type="submit"
                className="p-3 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-2xl hover:scale-105 active:scale-95 transition-all shrink-0"
              >
                <Plus size={20} />
              </button>
            </form>

            <ul className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
              <AnimatePresence>
                {(settings.do_rules || []).map((rule: string, idx: number) => (
                  <motion.li 
                    key={rule + idx}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex items-start justify-between gap-4 p-4 bg-white/[0.01] border border-white/5 rounded-2xl hover:border-white/10 transition-all text-sm group"
                  >
                    <span className="text-zinc-300 font-semibold">{rule}</span>
                    <button 
                      onClick={() => handleRemoveDoRule(idx)}
                      className="p-1 hover:bg-red-500/10 rounded text-zinc-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </div>

          {/* DONT Rules */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <div className="flex items-center justify-between border-b border-white/5 pb-4">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Trash2 size={16} className="text-red-500" />
                Negative / Behavioral Constraints (Don't Rules)
              </h3>
            </div>

            <form onSubmit={handleAddDontRule} className="flex gap-4">
              <input 
                type="text"
                value={newDontRule}
                onChange={(e) => setNewDontRule(e.target.value)}
                placeholder="Add constraint (e.g., Never start replies with 'Certainly'...)"
                className="flex-1 bg-white/5 border border-white/5 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10"
              />
              <button 
                type="submit"
                className="p-3 bg-red-500 hover:bg-red-600 text-black font-bold rounded-2xl hover:scale-105 active:scale-95 transition-all shrink-0"
              >
                <Plus size={20} />
              </button>
            </form>

            <ul className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
              <AnimatePresence>
                {(settings.dont_rules || []).map((rule: string, idx: number) => (
                  <motion.li 
                    key={rule + idx}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex items-start justify-between gap-4 p-4 bg-white/[0.01] border border-white/5 rounded-2xl hover:border-white/10 transition-all text-sm group"
                  >
                    <span className="text-zinc-300 font-semibold">{rule}</span>
                    <button 
                      onClick={() => handleRemoveDontRule(idx)}
                      className="p-1 hover:bg-red-500/10 rounded text-zinc-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </div>

          {/* Filesystem Folder Watcher */}
          <div className="glass p-6 rounded-[2rem] border border-white/5 space-y-6">
            <div className="flex items-center justify-between border-b border-white/5 pb-4">
              <div className="space-y-1">
                <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                  <Folder size={16} className="text-emerald-500" />
                  Auto-Indexing Folder Watcher
                </h3>
                <p className="text-[10px] text-zinc-500">
                  Monitor folders for changes. Added or modified files are automatically chunked and indexed into the selected RAG project.
                </p>
              </div>
            </div>

            {/* Add Watcher Form */}
            <form onSubmit={handleAddWatcher} className="grid grid-cols-1 md:grid-cols-12 gap-4 bg-white/[0.01] p-4 rounded-2xl border border-white/5">
              <div className="md:col-span-4">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Directory Path</label>
                <input 
                  type="text"
                  value={watcherPath}
                  onChange={(e) => setWatcherPath(e.target.value)}
                  placeholder="C:\Users\username\Documents"
                  className="w-full bg-white/5 border border-white/5 rounded-xl px-3 py-2 text-xs text-white placeholder:text-zinc-600 focus:ring-0 focus:border-white/10"
                />
              </div>

              <div className="md:col-span-3">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Target RAG Project</label>
                <select 
                  value={watcherProject}
                  onChange={(e) => setWatcherProject(e.target.value)}
                  className="w-full bg-zinc-950 border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-0 focus:border-white/10"
                >
                  <option value="default">default</option>
                  {projects.map((p: any) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div className="md:col-span-2">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Extensions</label>
                <input 
                  type="text"
                  value={watcherExtensions}
                  onChange={(e) => setWatcherExtensions(e.target.value)}
                  placeholder=".txt,.md"
                  className="w-full bg-white/5 border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-0 focus:border-white/10"
                />
              </div>

              <div className="md:col-span-1">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">Debounce (s)</label>
                <input 
                  type="number"
                  value={watcherDebounce}
                  onChange={(e) => setWatcherDebounce(Number(e.target.value))}
                  className="w-full bg-white/5 border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-0 focus:border-white/10"
                />
              </div>

              <div className="md:col-span-2 flex items-end">
                <button 
                  type="submit"
                  className="w-full py-2 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-xl text-xs hover:scale-105 active:scale-95 transition-all flex items-center justify-center gap-1.5"
                >
                  <FolderPlus size={14} />
                  Watch
                </button>
              </div>

              <div className="md:col-span-12 flex items-center gap-2">
                <input 
                  type="checkbox"
                  id="recursive"
                  checked={watcherRecursive}
                  onChange={(e) => setWatcherRecursive(e.target.checked)}
                  className="rounded bg-zinc-950 border border-white/5 text-emerald-500 focus:ring-0"
                />
                <label htmlFor="recursive" className="text-[10px] font-bold text-zinc-400 cursor-pointer select-none">
                  Watch Subdirectories (Recursive mode)
                </label>
              </div>
            </form>

            {/* List of Watched Directories */}
            <div className="space-y-2">
              {isWatcherLoading ? (
                <div className="text-center py-4 text-xs text-zinc-500">Loading watched folders...</div>
              ) : watchedDirs.length === 0 ? (
                <div className="text-center py-6 text-xs text-zinc-500 border border-dashed border-white/5 rounded-2xl">
                  No folders are currently being watched.
                </div>
              ) : (
                <div className="space-y-3">
                  {watchedDirs.map((dir: any) => (
                    <div 
                      key={dir.id}
                      className={cn(
                        "flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl border transition-all text-xs",
                        dir.enabled ? "bg-white/[0.01] border-white/5" : "bg-white/[0.005] border-white/5 opacity-50"
                      )}
                    >
                      <div className="space-y-1.5 max-w-full overflow-hidden">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-white text-xs bg-zinc-900 border border-white/5 px-2 py-0.5 rounded break-all">
                            {dir.path}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2 items-center text-[10px] text-zinc-400">
                          <span className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">
                            Project: {dir.project_id}
                          </span>
                          <span className="bg-zinc-800 px-1.5 py-0.5 rounded">
                            Exts: {dir.allowed_extensions || "*"}
                          </span>
                          <span className="bg-zinc-800 px-1.5 py-0.5 rounded">
                            {dir.recursive ? "Recursive" : "Shallow"}
                          </span>
                          <span className="bg-zinc-800 px-1.5 py-0.5 rounded">
                            Debounce: {dir.debounce_seconds}s
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {/* Toggle Enabled */}
                        <button
                          onClick={() => handleToggleWatcher(dir)}
                          className={cn(
                            "px-2.5 py-1.5 rounded-lg border text-[10px] font-bold tracking-wider transition-colors",
                            dir.enabled 
                              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20"
                              : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700"
                          )}
                        >
                          {dir.enabled ? "ACTIVE" : "PAUSED"}
                        </button>

                        {/* Trigger Scan */}
                        <button
                          onClick={() => handleScanWatcher(dir.id)}
                          disabled={!dir.enabled}
                          title="Scan directory now"
                          className="p-2 bg-white/5 border border-white/5 hover:bg-white/10 rounded-lg text-zinc-300 transition-all disabled:opacity-50"
                        >
                          <RefreshCw size={12} className="hover:rotate-180 transition-transform duration-500" />
                        </button>

                        {/* Delete */}
                        <button 
                          onClick={() => handleDeleteWatcher(dir.id)}
                          className="p-2 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 rounded-lg text-zinc-500 hover:text-red-400 transition-all"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
};
