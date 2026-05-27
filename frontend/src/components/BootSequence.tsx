"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

/* ══════════════════════════════════════════════════════════════════════
   BOOT SEQUENCE — Cinematic cold-boot overlay for ASTRA OS.
   
   Plays once per browser session. Cached via sessionStorage.
   Makes the first impression unforgettable.
   
   Uses Framer Motion instead of GSAP for consistency with the rest
   of the codebase (avoids adding GSAP complexity for a single component).
   ══════════════════════════════════════════════════════════════════════ */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";
const HEALTH_URL = API_BASE.replace("/api/v1", "") + "/health";

interface DiagnosticLine {
  label: string;
  dots: string;
  successText: string;
  status: "pending" | "ok" | "warn";
}

const DIAGNOSTICS: Omit<DiagnosticLine, "status">[] = [
  { label: "SQLite core tables", dots: "............", successText: "verified" },
  { label: "Ollama neural engine", dots: "..........", successText: "connected" },
  { label: "Vector memory store", dots: "...........", successText: "online" },
  { label: "Safety protocols", dots: "..............", successText: "armed" },
  { label: "Watcher filesystem hooks", dots: "......", successText: "active" },
  { label: "Scheduler service", dots: ".............", successText: "running" },
  { label: "Auth token", dots: "..................", successText: "cached" },
];

interface BootSequenceProps {
  children: React.ReactNode;
  onComplete: () => void;
}

export const BootSequence = ({ children, onComplete }: BootSequenceProps) => {
  // Start with null to avoid hydration mismatch — server and client
  // both render the same "loading" state until useEffect resolves.
  const [showBoot, setShowBoot] = useState<boolean | null>(null);

  const [phase, setPhase] = useState(0);
  const [lines, setLines] = useState<DiagnosticLine[]>([]);
  const [visibleLines, setVisibleLines] = useState(0);
  const [showReady, setShowReady] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [showSkip, setShowSkip] = useState(false);
  const completedRef = useRef(false);

  // Hydration-safe: check sessionStorage only on the client after mount
  useEffect(() => {
    const alreadyBooted = sessionStorage.getItem("astra-booted");
    if (alreadyBooted) {
      setShowBoot(false);
      onComplete();
    } else {
      setShowBoot(true);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const finishBoot = useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    setExiting(true);
    setTimeout(() => {
      sessionStorage.setItem("astra-booted", "1");
      onComplete();
    }, 800);
  }, [onComplete]);

  // ── Phase progression ─────────────────────────────────────────

  useEffect(() => {
    // Only start boot phases when explicitly determined to show boot
    if (showBoot !== true) return;

    // Phase 0 → 1: Black void → Grid + header (500ms)
    const t1 = setTimeout(() => setPhase(1), 500);

    // Show skip button after 1.5s
    const tSkip = setTimeout(() => setShowSkip(true), 1500);

    // Phase 1 → 2: Start diagnostics (2s)
    const t2 = setTimeout(() => {
      setPhase(2);
      runDiagnostics();
    }, 2000);

    return () => {
      clearTimeout(t1);
      clearTimeout(tSkip);
      clearTimeout(t2);
    };
  }, [showBoot]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Diagnostic API checks with 3s timeout ─────────────────────

  const runDiagnostics = useCallback(async () => {
    // First: check health endpoint (determines if backend is alive)
    let backendAlive = false;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(HEALTH_URL, { signal: controller.signal });
      clearTimeout(timeout);
      backendAlive = res.ok;
    } catch {
      backendAlive = false;
    }

    // Second: try to cache auth token
    let tokenCached = false;
    if (backendAlive) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(`${API_BASE}/auth/token`, { signal: controller.signal });
        clearTimeout(timeout);
        tokenCached = res.ok;
      } catch {
        tokenCached = false;
      }
    }

    // Build diagnostic results
    const results: DiagnosticLine[] = DIAGNOSTICS.map((d, i) => ({
      ...d,
      status: ((): "ok" | "warn" => {
        // Line 0 (SQLite): always ok if we got this far
        if (i === 0) return "ok";
        // Line 1 (Ollama): depends on health check
        if (i === 1) return backendAlive ? "ok" : "warn";
        // Lines 2-5: depend on backend being alive
        if (i >= 2 && i <= 5) return backendAlive ? "ok" : "warn";
        // Line 6 (Auth token): depends on token fetch
        if (i === 6) return tokenCached ? "ok" : "warn";
        return "ok";
      })(),
    }));

    setLines(results);

    // Stagger reveal lines (120ms each)
    for (let i = 0; i < results.length; i++) {
      await new Promise((r) => setTimeout(r, 120));
      setVisibleLines(i + 1);
    }

    // Phase 3: All lines visible → show READY message
    await new Promise((r) => setTimeout(r, 600));
    setShowReady(true);
    setPhase(3);

    // Phase 4: Exit after 1.2s
    await new Promise((r) => setTimeout(r, 1200));
    finishBoot();
  }, [finishBoot]);

  // ── SSR / pre-hydration: render a void screen to prevent flash ──

  if (showBoot === null) {
    return (
      <div className="w-full h-screen bg-[var(--color-void)]" />
    );
  }

  // ── Already booted (sessionStorage found): render children directly ──

  if (showBoot === false) {
    return <>{children}</>;
  }

  return (
    <>
      {/* The app renders behind the overlay */}
      <div className={cn(exiting ? "opacity-100" : "opacity-0", "transition-opacity duration-500")}>
        {children}
      </div>

      {/* Boot Overlay */}
      <AnimatePresence>
        {!completedRef.current && (
          <motion.div
            initial={{ opacity: 1 }}
            animate={exiting ? { clipPath: "inset(50% 0)" } : { clipPath: "inset(0% 0)" }}
            transition={{ duration: 0.8, ease: [0.65, 0, 0.35, 1] }}
            className="fixed inset-0 z-50 bg-[var(--color-void)] flex flex-col items-center justify-center overflow-hidden"
          >
            {/* Grid backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: phase >= 1 ? 1 : 0 }}
              transition={{ duration: 1 }}
              className="absolute inset-0 bg-grid opacity-30"
            />

            {/* Content container */}
            <div className="relative z-10 w-full max-w-xl px-8">
              {/* Boot header */}
              <AnimatePresence>
                {phase >= 1 && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="mb-8"
                  >
                    <h1 className="font-terminal text-[var(--color-accent-cyan)] text-sm tracking-[0.3em] uppercase">
                      ASTRA OS v0.4.0
                    </h1>
                    <p className="font-terminal text-[var(--color-text-muted)] text-xs mt-1 tracking-wider">
                      // KERNEL INITIALIZATION
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Diagnostic lines */}
              <div className="space-y-1 font-terminal text-[13px]">
                {lines.slice(0, visibleLines).map((line, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.15, ease: "easeOut" }}
                    className="flex items-center gap-0"
                  >
                    <span
                      className={cn(
                        "w-[52px] shrink-0 font-bold",
                        line.status === "ok"
                          ? "text-emerald-500"
                          : "text-amber-500"
                      )}
                    >
                      [{line.status === "ok" ? "OK" : "WARN"}]
                    </span>
                    <span className="text-[var(--color-text-body)] whitespace-nowrap">
                      {line.label}
                    </span>
                    <span className="text-[var(--color-text-muted)] mx-1 tracking-[0.2em] whitespace-nowrap overflow-hidden">
                      {line.dots}
                    </span>
                    <span
                      className={cn(
                        "whitespace-nowrap",
                        line.status === "ok"
                          ? "text-[var(--color-text-body)]"
                          : "text-amber-500/70"
                      )}
                    >
                      {line.status === "ok" ? line.successText : "connecting..."}
                    </span>
                  </motion.div>
                ))}
              </div>

              {/* SYSTEM READY */}
              <AnimatePresence>
                {showReady && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.2 }}
                    className="mt-10 text-center"
                  >
                    <p className="text-[var(--color-text-bright)] font-bold text-sm tracking-[0.2em] uppercase font-terminal">
                      SYSTEM READY
                    </p>
                    <p className="text-[var(--color-text-muted)] text-xs mt-1 font-terminal tracking-wider">
                      // ENTERING COMMAND CENTER
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Skip button — appears after 1.5s */}
            <AnimatePresence>
              {showSkip && !showReady && (
                <motion.button
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 0.3 }}
                  whileHover={{ opacity: 0.6 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  onClick={finishBoot}
                  className="fixed bottom-6 right-8 z-50 text-[11px] font-terminal text-[var(--color-text-muted)] tracking-wider hover:text-[var(--color-text-body)] transition-colors"
                >
                  skip →
                </motion.button>
              )}
            </AnimatePresence>

            {/* Ambient glow */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[var(--color-accent-cyan)] opacity-[0.02] blur-[150px] pointer-events-none" />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
