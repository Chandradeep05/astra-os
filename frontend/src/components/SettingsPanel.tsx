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
  UserCheck
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

export const SettingsPanel = () => {
  const [settings, setSettings] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  // Input states for adding new rules
  const [newDoRule, setNewDoRule] = useState("");
  const [newDontRule, setNewDontRule] = useState("");

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

  useEffect(() => {
    fetchSettings();
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

        </div>

      </div>

    </div>
  );
};
