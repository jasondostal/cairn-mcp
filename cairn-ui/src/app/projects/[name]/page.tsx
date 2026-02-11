"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { Download, LayoutList, LayoutGrid, FileText, ArrowLeft } from "lucide-react";

interface ProjectDetail {
  name: string;
  docs: Array<Record<string, unknown>>;
  links: Array<Record<string, unknown>>;
}

function ProjectDocs({ docs }: { docs: Array<Record<string, unknown>> }) {
  const [dense, setDense] = useState(true);
  const [filter, setFilter] = useState("");

  const filtered = docs.filter((doc) => {
    if (!filter) return true;
    const f = filter.toLowerCase();
    const title = (doc.title as string) || "";
    const type = (doc.doc_type as string) || "";
    const content = (doc.content as string) || "";
    return (
      title.toLowerCase().includes(f) ||
      type.toLowerCase().includes(f) ||
      content.toLowerCase().includes(f)
    );
  });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">
          Documents ({filtered.length}{filter ? ` of ${docs.length}` : ""})
        </h2>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Filter..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-7 w-32 text-xs"
          />
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setDense(!dense)}
            title={dense ? "Expanded view" : "Dense view"}
          >
            {dense ? <LayoutGrid className="h-3.5 w-3.5" /> : <LayoutList className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {docs.length === 0 ? "No documents yet." : "No documents match filter."}
        </p>
      ) : dense ? (
        <div className="rounded-md border border-border divide-y divide-border">
          {filtered.map((doc, i) => {
            const title = (doc.title as string) || (doc.content as string)?.match(/^#\s+(.+)$/m)?.[1] || `Untitled ${doc.doc_type}`;
            return (
              <Link
                key={i}
                href={doc.id ? `/docs/${doc.id}` : "#"}
                className="flex items-center gap-3 px-3 py-2 hover:bg-accent/50 transition-colors text-sm"
              >
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate">{title}</span>
                <DocTypeBadge type={(doc.doc_type as string) || "doc"} />
                {doc.created_at ? (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {formatDate(doc.created_at as string)}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((doc, i) => (
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
                  {(doc.content as string) || "\u2014"}
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
  );
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

  return (
    <PageLayout
      title={project?.name ?? name}
      titleExtra={<>
        {project && <ExportButton project={project.name} />}
        <Link href="/projects">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
      </>}
    >
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-40" />
        </div>
      )}

      {!loading && error && <ErrorState message="Failed to load project" detail={error} />}

      {!loading && !error && !project && <EmptyState message="Project not found." />}

      {!loading && !error && project && (
        <div className="space-y-6 max-w-3xl">
          <ProjectDocs docs={project.docs} />

          <div>
            <h2 className="mb-3 text-sm font-medium text-muted-foreground">
              Links ({project.links.length})
            </h2>
            {project.links.length === 0 ? (
              <EmptyState message="No links." />
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
      )}
    </PageLayout>
  );
}
