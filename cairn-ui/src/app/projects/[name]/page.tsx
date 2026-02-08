"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { Download } from "lucide-react";

interface ProjectDetail {
  name: string;
  docs: Array<Record<string, unknown>>;
  links: Array<Record<string, unknown>>;
}

function ExportButton({ project }: { project: string }) {
  const [exporting, setExporting] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  async function doExport(format: "json" | "markdown") {
    setShowMenu(false);
    setExporting(true);
    try {
      const url = new URL("/api/export", window.location.origin);
      url.searchParams.set("project", project);
      url.searchParams.set("format", format);

      const res = await fetch(url.toString());
      if (!res.ok) throw new Error(`${res.status}`);

      const blob = await res.blob();
      const ext = format === "markdown" ? "md" : "json";
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${project}-export.${ext}`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch {
      // Silently fail — the fetch error is visible in devtools
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        disabled={exporting}
        onClick={() => setShowMenu(!showMenu)}
      >
        <Download className="mr-1.5 h-4 w-4" />
        {exporting ? "Exporting\u2026" : "Export"}
      </Button>
      {showMenu && (
        <div className="absolute right-0 top-full z-10 mt-1 rounded-md border border-border bg-popover p-1 shadow-md">
          <button
            onClick={() => doExport("json")}
            className="block w-full rounded-sm px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
          >
            JSON
          </button>
          <button
            onClick={() => doExport("markdown")}
            className="block w-full rounded-sm px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
          >
            Markdown
          </button>
        </div>
      )}
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const name = decodeURIComponent(params.name as string);
  const { data: project, loading, error } = useFetch<ProjectDetail>(
    () => api.project(name),
    [name]
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message="Failed to load project" detail={error} />;
  }

  if (!project) {
    return <p className="text-sm text-muted-foreground">Project not found.</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{project.name}</h1>
        <ExportButton project={project.name} />
      </div>

      {/* Documents */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Documents ({project.docs.length})
        </h2>
        {project.docs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents yet.</p>
        ) : (
          <div className="space-y-3">
            {project.docs.map((doc, i) => (
              <Card key={i}>
                <CardHeader className="p-4 pb-2">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">
                      {(doc.doc_type as string) || "Document"}
                    </CardTitle>
                    {doc.doc_type ? (
                      <Badge variant="outline" className="text-xs">
                        {String(doc.doc_type)}
                      </Badge>
                    ) : null}
                  </div>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <p className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                    {(doc.content as string) || "—"}
                  </p>
                  {doc.created_at ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {formatDate(doc.created_at as string)}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Links */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Links ({project.links.length})
        </h2>
        {project.links.length === 0 ? (
          <p className="text-sm text-muted-foreground">No links.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {project.links.map((link, i) => (
              <Badge key={i} variant="secondary" className="gap-1">
                {(link.target as string) || "unknown"}
                <span className="text-muted-foreground">
                  ({(link.link_type as string) || "related"})
                </span>
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
