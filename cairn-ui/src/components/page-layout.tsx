import React from "react";

interface PageLayoutProps {
  title: string;
  titleExtra?: React.ReactNode;
  filters?: React.ReactNode;
  children: React.ReactNode;
}

export function PageLayout({ title, titleExtra, filters, children }: PageLayoutProps) {
  return (
    <div
      className="flex flex-col -m-4 md:-m-6"
      style={{ height: "calc(100vh - var(--removed, 0px))" }}
    >
      {/* Fixed header — never scrolls */}
      <div className="shrink-0 px-4 md:px-6 pt-4 md:pt-6 pb-3 border-b border-border bg-background">
        <div className={`flex items-center justify-between${filters ? " mb-3" : ""}`}>
          <h1 className="text-2xl font-semibold">{title}</h1>
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
