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
    <div className="flex flex-col h-full -m-4 md:-m-6">
      {/* Fixed header — never scrolls */}
      <div className="shrink-0 px-4 md:px-6 pt-4 md:pt-6 pb-3 border-b border-border bg-background">
        <div className={`flex items-center justify-between${filters ? " mb-3" : ""}`}>
          <h1 className="flex items-center gap-2.5 text-2xl font-semibold">
            {Icon && <Icon className="h-6 w-6" style={iconColor ? { color: iconColor } : undefined} />}
            {title}
          </h1>
          {titleExtra && <div className="flex items-center gap-2">{titleExtra}</div>}
        </div>
        {filters}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 md:px-6 pt-4 pb-4">
        {children}
      </div>
    </div>
  );
}
