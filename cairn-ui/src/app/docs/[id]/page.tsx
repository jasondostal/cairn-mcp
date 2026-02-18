"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Document } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { DownloadMenu } from "@/components/download-menu";
import { triggerDownload, sanitizeFilename } from "@/lib/download";
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
  const [pdfBusy, setPdfBusy] = useState(false);
  const articleRef = useRef<HTMLElement>(null);

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

  const title = doc ? extractTitle(doc) : "Document";

  function downloadMarkdown() {
    if (!doc) return;
    const filename = `${sanitizeFilename(title)}.md`;
    const content = doc.title ? `# ${doc.title}\n\n${doc.content}` : doc.content;
    triggerDownload(content, filename, "text/markdown");
  }

  async function downloadPdf() {
    if (!doc || !articleRef.current) return;
    setPdfBusy(true);
    try {
      const html2pdf = (await import("html2pdf.js")).default;
      // Clone and restyle for light-mode PDF output
      const clone = articleRef.current.cloneNode(true) as HTMLElement;
      clone.style.color = "#111";
      clone.style.background = "#fff";
      clone.querySelectorAll("*").forEach((el) => {
        const htmlEl = el as HTMLElement;
        htmlEl.style.color = "#111";
      });

      const filename = `${sanitizeFilename(title)}.pdf`;
      await html2pdf()
        .set({
          margin: [12, 12, 12, 12],
          filename,
          image: { type: "jpeg", quality: 0.95 },
          html2canvas: { scale: 2, useCORS: true },
          jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
        })
        .from(clone)
        .save();
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <PageLayout
      title={title}
      titleExtra={<>
        {doc && (
          <DownloadMenu
            options={[
              { label: "Markdown (.md)", onClick: downloadMarkdown },
              { label: pdfBusy ? "Generating PDF\u2026" : "PDF (.pdf)", onClick: downloadPdf },
            ]}
          />
        )}
        <Link href="/docs">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
      </>}
    >
      {loading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-6 w-48 bg-muted rounded" />
          <div className="h-4 w-32 bg-muted rounded" />
          <div className="space-y-2 mt-8">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-4 bg-muted rounded" style={{ width: `${70 + (i * 17 % 30)}%` }} />
            ))}
          </div>
        </div>
      )}

      {!loading && error && <ErrorState message="Failed to load document" detail={error} />}

      {!loading && !error && !doc && <EmptyState message="Document not found." />}

      {!loading && !error && doc && (
        <div className="space-y-6">
          <div className="flex items-center gap-2">
            <DocTypeBadge type={doc.doc_type} />
            <Link href={`/projects/${encodeURIComponent(doc.project)}`}>
              <Badge variant="secondary" className="text-xs hover:bg-secondary/80 cursor-pointer">{doc.project}</Badge>
            </Link>
            <span className="text-xs text-muted-foreground">{formatDate(doc.updated_at)}</span>
          </div>

          <article ref={articleRef} className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.content}</ReactMarkdown>
          </article>
        </div>
      )}
    </PageLayout>
  );
}
