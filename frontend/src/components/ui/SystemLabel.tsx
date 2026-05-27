"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface SystemLabelProps {
  children: React.ReactNode;
  className?: string;
  size?: "xs" | "sm" | "md";
  color?: "muted" | "body" | "bright" | "cyan" | "purple" | "emerald" | "amber";
  icon?: React.ReactNode;
  mono?: boolean;
}

const sizeClasses = {
  xs: "text-[9px] tracking-[0.2em]",
  sm: "text-[10px] tracking-[0.15em]",
  md: "text-xs tracking-[0.1em]",
};

const colorClasses = {
  muted: "text-[var(--color-text-muted)]",
  body: "text-[var(--color-text-body)]",
  bright: "text-[var(--color-text-bright)]",
  cyan: "text-cyan-500",
  purple: "text-purple-400",
  emerald: "text-emerald-500",
  amber: "text-amber-500",
};

export const SystemLabel = ({
  children,
  className,
  size = "sm",
  color = "muted",
  icon,
  mono = false,
}: SystemLabelProps) => {
  return (
    <span
      className={cn(
        "font-bold uppercase inline-flex items-center gap-1.5",
        sizeClasses[size],
        colorClasses[color],
        mono && "font-terminal",
        className
      )}
    >
      {icon}
      {children}
    </span>
  );
};
