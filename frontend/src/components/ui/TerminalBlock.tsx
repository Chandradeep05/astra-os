"use client";

import React, { useState, useRef, useCallback } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface TerminalBlockProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  copyable?: boolean;
  maxHeight?: string;
  animate?: boolean;
}

export const TerminalBlock = ({
  children,
  className,
  title,
  copyable = true,
  maxHeight = "300px",
  animate = false,
}: TerminalBlockProps) => {
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLPreElement>(null);

  const handleCopy = useCallback(() => {
    if (contentRef.current) {
      const text = contentRef.current.textContent || "";
      navigator.clipboard.writeText(text).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  }, []);

  return (
    <div
      className={cn(
        "relative rounded-xl overflow-hidden",
        "bg-[var(--color-void)] border border-[var(--color-border-subtle)]",
        className
      )}
    >
      {/* Header */}
      {(title || copyable) && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface)]/50">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500/60" />
              <span className="w-2 h-2 rounded-full bg-amber-500/60" />
              <span className="w-2 h-2 rounded-full bg-emerald-500/60" />
            </div>
            {title && (
              <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)] ml-2">
                {title}
              </span>
            )}
          </div>
          {copyable && (
            <button
              onClick={handleCopy}
              className="p-1 rounded hover:bg-white/5 text-[var(--color-text-muted)] hover:text-[var(--color-text-body)] transition-colors duration-[var(--motion-hover)]"
              title="Copy to clipboard"
            >
              {copied ? (
                <Check size={12} className="text-emerald-500" />
              ) : (
                <Copy size={12} />
              )}
            </button>
          )}
        </div>
      )}

      {/* Content */}
      <pre
        ref={contentRef}
        className={cn(
          "p-4 overflow-auto font-terminal text-[13px] leading-relaxed text-[var(--color-text-body)]",
          animate && "animate-fade-in-up"
        )}
        style={{ maxHeight }}
      >
        {children}
      </pre>
    </div>
  );
};
