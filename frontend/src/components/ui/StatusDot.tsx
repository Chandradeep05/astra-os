"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface StatusDotProps {
  status: "online" | "offline" | "sleeping" | "thinking" | "executing" | "warning" | "error";
  size?: "sm" | "md" | "lg";
  pulse?: boolean;
  className?: string;
}

const statusColors: Record<StatusDotProps["status"], string> = {
  online: "bg-emerald-500 text-emerald-500",
  offline: "bg-zinc-600 text-zinc-600",
  sleeping: "bg-indigo-400 text-indigo-400",
  thinking: "bg-cyan-500 text-cyan-500",
  executing: "bg-cyan-400 text-cyan-400",
  warning: "bg-amber-500 text-amber-500",
  error: "bg-red-500 text-red-500",
};

const statusGlows: Record<StatusDotProps["status"], string> = {
  online: "shadow-[0_0_8px_rgba(16,185,129,0.5)]",
  offline: "",
  sleeping: "shadow-[0_0_8px_rgba(129,140,248,0.3)]",
  thinking: "shadow-[0_0_10px_rgba(6,182,212,0.5)]",
  executing: "shadow-[0_0_12px_rgba(6,182,212,0.6)]",
  warning: "shadow-[0_0_8px_rgba(245,158,11,0.5)]",
  error: "shadow-[0_0_8px_rgba(239,68,68,0.5)]",
};

const sizeClasses = {
  sm: "w-1.5 h-1.5",
  md: "w-2.5 h-2.5",
  lg: "w-3.5 h-3.5",
};

export const StatusDot = ({
  status,
  size = "md",
  pulse = true,
  className,
}: StatusDotProps) => {
  const shouldPulse = pulse && status !== "offline" && status !== "sleeping";

  return (
    <span className={cn("relative inline-flex", className)}>
      <span
        className={cn(
          "rounded-full",
          sizeClasses[size],
          statusColors[status],
          statusGlows[status],
          shouldPulse && "animate-status-pulse"
        )}
      />
      {shouldPulse && (
        <span
          className={cn(
            "absolute inset-0 rounded-full opacity-40 animate-ping",
            statusColors[status]
          )}
        />
      )}
    </span>
  );
};
