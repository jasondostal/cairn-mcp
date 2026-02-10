"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Document } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { ProjectSelector } from "@/components/project-selector";
import { SkeletonList } from "@/components/skeleton-list";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { FileText, LayoutList, LayoutGrid } from "lucide-react";

const DOC_TYPES = ["brief", "prd", "plan", "primer", "writeup", "guide"] as const;

function extractTitle(doc: Document): string {
  if (doc.title) return doc.title;
  const match = doc.content.match(/^#\s+(.+)$/m);
  return match ? match[1] : `Untitled ${doc.doc_type}`;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+.*$/gm, "")
    .replace(/[*_`~\[\]]/g, "")
    .replace(/\n+/g, " ")
    .trim();
}

function DocDenseRow({ doc, showProject }: { doc: Document; showProject?: boolean }) {
  const title = extractTitle(doc);
  return (
    <Link
      href={`/docs/${doc.id}`}
      className="flex items-center gap-3 px-3 py-2 hover:bg-accent/50 transition-colors text-sm"
    >
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate">{title}</span>
      <DocTypeBadge type={doc.doc_type} />
      {showProject && (
        <Badge variant="secondary" className="text-xs shrink-0">{doc.project}</Badge>
      )}
      <span className="text-xs text-muted-foreground shrink-0">
        {formatDate(doc.updated_at)}
      </span>
    </Link>
  );
}

function DocCard({ doc, showProject }: { doc: Document; showProject?: boolean }) {
  const title = extractTitle(doc);
  const preview = stripMarkdown(doc.content).slice(0, 150);

  return (
    <Link href={`/docs/${doc.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardContent className="p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <h3 className="text-sm font-medium truncate">{title}</h3>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <DocTypeBadge type={doc.doc_type} />
              {showProject && (
                <Badge variant="secondary" className="text-xs">
                  {doc.project}
                </Badge>
              )}
            </div>
          </div>

          {preview && (
            <p className="text-sm text-muted-foreground line-clamp-2">{preview}</p>
          )}

          <div className="text-xs text-muted-foreground">
            {formatDate(doc.updated_at)}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function DocsPage() {
  const { projects, selected, setSelected, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [dense, setDense] = useState(true);

  useEffect(() => {
    if (!showAll && !selected) return;
    setLoading(true);
    setError(null);
    api
      .docs({
        project: showAll ? undefined : selected,
        doc_type: typeFilter ?? undefined,
      })
      .then((r) => setDocs(r.items))
      .catch((err) => setError(err?.message || "Failed to load docs"))
      .finally(() => setLoading(false));
  }, [selected, showAll, typeFilter]);

  function handleShowAll() {
    setShowAll(true);
  }

  function handleSelectProject(name: string) {
    setShowAll(false);
    setSelected(name);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Docs</h1>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={() => setDense(!dense)}
          title={dense ? "Card view" : "Dense view"}
        >
          {dense ? <LayoutGrid className="h-4 w-4" /> : <LayoutList className="h-4 w-4" />}
        </Button>
      </div>

      <div className="flex gap-1 flex-wrap">
        <Button
          variant={showAll ? "default" : "outline"}
          size="sm"
          onClick={handleShowAll}
        >
          All
        </Button>
        <ProjectSelector
          projects={projects}
          selected={showAll ? "" : selected}
          onSelect={handleSelectProject}
        />
      </div>

      <div className="flex gap-1 flex-wrap">
        <Button
          variant={typeFilter === null ? "default" : "outline"}
          size="sm"
          onClick={() => setTypeFilter(null)}
        >
          All types
        </Button>
        {DOC_TYPES.map((t) => (
          <Button
            key={t}
            variant={typeFilter === t ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter(t)}
          >
            {t}
          </Button>
        ))}
      </div>

      {(loading || projectsLoading) && <SkeletonList count={4} height="h-24" />}

      {(error || projectsError) && <ErrorState message="Failed to load docs" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && docs.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No documents found.
        </p>
      )}

      {!loading && !projectsLoading && !error && !projectsError && docs.length > 0 && (
        dense ? (
          <div className="rounded-md border border-border divide-y divide-border">
            {docs.map((d) => (
              <DocDenseRow key={d.id} doc={d} showProject={showAll} />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((d) => (
              <DocCard key={d.id} doc={d} showProject={showAll} />
            ))}
          </div>
        )
      )}
    </div>
  );
}
