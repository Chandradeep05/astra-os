"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
  intensity?: "surface" | "panel" | "elevated" | "dark";
  padding?: "none" | "sm" | "md" | "lg" | "xl";
  rounded?: "md" | "lg" | "xl" | "2xl" | "3xl";
  hover?: boolean;
  onClick?: () => void;
}

const intensityClasses = {
  surface: "glass-surface",
  panel: "glass-panel",
  elevated: "glass-elevated",
  dark: "glass-dark",
};

const paddingClasses = {
  none: "",
  sm: "p-3",
  md: "p-5",
  lg: "p-6",
  xl: "p-8",
};

const roundedClasses = {
  md: "rounded-xl",
  lg: "rounded-2xl",
  xl: "rounded-[1.5rem]",
  "2xl": "rounded-[2rem]",
  "3xl": "rounded-[2.5rem]",
};

export const GlassPanel = ({
  children,
  className,
  intensity = "panel",
  padding = "md",
  rounded = "xl",
  hover = false,
  onClick,
}: GlassPanelProps) => {
  return (
    <div
      className={cn(
        intensityClasses[intensity],
        paddingClasses[padding],
        roundedClasses[rounded],
        hover &&
          "hover:border-white/15 transition-all duration-[var(--motion-hover)] cursor-pointer",
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
};
