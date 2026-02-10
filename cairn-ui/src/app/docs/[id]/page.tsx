"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Document } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { ArrowLeft } from "lucide-react";

function extractTitle(doc: Document): string {
  if (doc.title) return doc.title;
  const match = doc.content.match(/^#\s+(.+)$/m);
  return match ? match[1] : `Untitled ${doc.doc_type}`;
}

export default function DocDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    api
      .doc(id)
      .then(setDoc)
      .catch((err) => setError(err?.message || "Failed to load document"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 w-48 bg-muted rounded" />
        <div className="h-4 w-32 bg-muted rounded" />
        <div className="space-y-2 mt-8">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-4 bg-muted rounded" style={{ width: `${70 + Math.random() * 30}%` }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) return <ErrorState message="Failed to load document" detail={error} />;
  if (!doc) return <ErrorState message="Document not found" />;

  const title = extractTitle(doc);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/docs">
          <Button variant="ghost" size="sm" className="gap-1 -ml-2 mb-4">
            <ArrowLeft className="h-4 w-4" />
            Back to docs
          </Button>
        </Link>

        <h1 className="text-2xl font-semibold">{title}</h1>

        <div className="flex items-center gap-2 mt-2">
          <DocTypeBadge type={doc.doc_type} />
          <Badge variant="secondary" className="text-xs">{doc.project}</Badge>
          <span className="text-xs text-muted-foreground">{formatDate(doc.updated_at)}</span>
        </div>
      </div>

      <article className="prose prose-invert prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.content}</ReactMarkdown>
      </article>
    </div>
  );
}
