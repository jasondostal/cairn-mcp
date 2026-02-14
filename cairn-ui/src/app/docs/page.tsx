"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Document } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { FileText } from "lucide-react";

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
  const filters = usePageFilters();
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const typeOptions = DOC_TYPES.map((t) => ({ value: t, label: t }));

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .docs({
        project: filters.showAllProjects ? undefined : filters.projectFilter.join(","),
        doc_type: filters.typeFilter.length ? filters.typeFilter.join(",") : undefined,
      })
      .then((r) => setDocs(r.items))
      .catch((err) => setError(err?.message || "Failed to load docs"))
      .finally(() => setLoading(false));
  }, [filters.projectFilter, filters.typeFilter, filters.showAllProjects]);

  return (
    <PageLayout
      title="Docs"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={
        <PageFilters
          filters={filters}
          typeOptions={typeOptions}
          typePlaceholder="All types"
        />
      }
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={4} height="h-24" />}

      {error && <ErrorState message="Failed to load docs" detail={error} />}

      {!loading && !filters.projectsLoading && !error && docs.length === 0 && (
        <EmptyState message="No documents found." />
      )}

      {!loading && !filters.projectsLoading && !error && docs.length > 0 && (
        filters.dense ? (
          <div className="rounded-md border border-border divide-y divide-border">
            {docs.map((d) => (
              <DocDenseRow key={d.id} doc={d} showProject={filters.showAllProjects} />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((d) => (
              <DocCard key={d.id} doc={d} showProject={filters.showAllProjects} />
            ))}
          </div>
        )
      )}
    </PageLayout>
  );
}
