"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { navItems } from "@/lib/nav";
import type { LucideIcon } from "lucide-react";

interface PageLayoutProps {
  title: string;
  icon?: LucideIcon;
  iconColor?: string;
  titleExtra?: React.ReactNode;
  filters?: React.ReactNode;
  children: React.ReactNode;
}

export function PageLayout({ title, icon, iconColor, titleExtra, filters, children }: PageLayoutProps) {
  const pathname = usePathname();

  // Auto-resolve icon from nav.ts when not explicitly provided
  const Icon = icon ?? (navItems.find((n) => n.href === pathname)?.icon as LucideIcon | undefined);

  return (
    <div className="flex flex-col h-full">
      {/* Compact header — title left, filters right on desktop; stacked on mobile */}
      <div className="shrink-0 px-3 md:px-6 py-2 md:py-3 border-b border-border bg-background">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-2 md:gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <h1 className="flex items-center gap-1.5 text-lg font-semibold">
              {Icon && <Icon className="h-4 w-4 md:h-5 md:w-5" style={iconColor ? { color: iconColor } : undefined} />}
              {title}
            </h1>
            {titleExtra && <div className="flex items-center gap-2">{titleExtra}</div>}
          </div>
          {filters && <div className="flex-1 min-w-0">{filters}</div>}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 md:px-6 pt-3 pb-4">
        <div className="mx-auto max-w-7xl">
          {children}
        </div>
      </div>
    </div>
  );
}
