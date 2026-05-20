"use client";

import React, { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatInterface } from "@/components/ChatInterface";
import { AstraAgent } from "@/components/AstraAgent";
import { Dashboard } from "@/components/Dashboard";
import { MemoryBrowser } from "@/components/MemoryBrowser";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AnimatePresence, motion } from "framer-motion";

export default function Home() {
  const [activeProjectId, setActiveProjectId] = useState("dashboard");
  const [activeProjectName, setActiveProjectName] = useState("Dashboard");

  const handleSelectProject = (id: string, label?: string) => {
    setActiveProjectId(id);
    if (label) setActiveProjectName(label);
  };

  return (
    <div className="flex w-full h-full bg-black overflow-hidden relative">
      <Sidebar 
        activeProject={activeProjectId} 
        onSelectProject={handleSelectProject} 
      />
      
      <main className="flex-1 min-w-0 bg-[#09090b] relative border-l border-white/5 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeProjectId === "dashboard" ? (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="h-full w-full"
            >
              <ErrorBoundary>
                <Dashboard onSelectProject={handleSelectProject} />
              </ErrorBoundary>
            </motion.div>
          ) : activeProjectId === "agent" ? (
            <motion.div
              key="agent"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.4, ease: "circOut" }}
              className="h-full w-full"
            >
              <ErrorBoundary>
                <AstraAgent />
              </ErrorBoundary>
            </motion.div>
          ) : activeProjectId === "memory-browser" ? (
            <motion.div
              key="memory-browser"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.4, ease: "circOut" }}
              className="h-full w-full"
            >
              <ErrorBoundary>
                <MemoryBrowser />
              </ErrorBoundary>
            </motion.div>
          ) : (
            <motion.div
              key={activeProjectId}
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.4, ease: "circOut" }}
              className="h-full w-full"
            >
              <ErrorBoundary>
                <ChatInterface project_id={activeProjectId} project_name={activeProjectName} />
              </ErrorBoundary>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      
      {/* Cinematic Background Accents */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-emerald-500/5 blur-[150px] rounded-full -translate-y-1/2 translate-x-1/2 pointer-events-none opacity-40 animate-pulse" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-blue-500/5 blur-[130px] rounded-full translate-y-1/2 -translate-x-1/2 pointer-events-none opacity-40" />
    </div>
  );
}
