"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, resolveCairnUrl, type Attachment, type Document } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { DocTypeBadge } from "@/components/doc-type-badge";
import { ProjectPill } from "@/components/project-pill";
import { DownloadMenu } from "@/components/download-menu";
import { ArrowLeft, Copy, ImagePlus, Trash2, Upload } from "lucide-react";
import { Breadcrumbs } from "@/components/breadcrumbs";

function extractTitle(doc: Document): string {
  if (doc.title) return doc.title;
  const match = doc.content.match(/^#\s+(.+)$/m);
  return match ? match[1] : `Untitled ${doc.doc_type}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Fetches an image with auth headers and renders it via a blob URL. */
function AuthImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoke: string | null = null;
    fetch(src, { headers: getAuthHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        revoke = url;
        setBlobUrl(url);
      })
      .catch(() => setBlobUrl(null));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [src]);

  if (!blobUrl) return <span className="text-xs text-muted-foreground italic">Loading image...</span>;
  return <img src={blobUrl} alt={alt} className={className} />;
}

export default function DocDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const articleRef = useRef<HTMLElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    if (!id) return;
    api.docAttachments(id).then(setAttachments).catch(() => {});
  }, [id]);

  const title = doc ? extractTitle(doc) : "Document";

  async function triggerServerDownload(path: string, filename: string) {
    const res = await fetch(path, { headers: getAuthHeaders() });
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadMarkdown() {
    if (!doc) return;
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    triggerServerDownload(`/api/docs/${doc.id}/md`, `${slug}.md`);
  }

  function downloadPdf() {
    if (!doc) return;
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    triggerServerDownload(`/api/docs/${doc.id}/pdf`, `${slug}.pdf`);
  }

  const handleUpload = useCallback(async (files: FileList | File[]) => {
    if (!doc) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const att = await api.uploadAttachment(doc.id, file);
        setAttachments((prev) => [...prev, att]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      alert(msg);
    } finally {
      setUploading(false);
    }
  }, [doc]);

  const handleDelete = useCallback(async (attId: number) => {
    await api.deleteAttachment(attId);
    setAttachments((prev) => prev.filter((a) => a.id !== attId));
  }, []);

  const copyMarkdownRef = useCallback((att: Attachment) => {
    navigator.clipboard.writeText(`![${att.filename}](${att.url})`);
    setCopied(att.id);
    setTimeout(() => setCopied(null), 2000);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  }, [handleUpload]);

  return (
    <PageLayout
      title={title}
      titleExtra={<>
        {doc && (
          <DownloadMenu
            options={[
              { label: "Markdown (.md)", onClick: downloadMarkdown },
              { label: "PDF (.pdf)", onClick: downloadPdf },
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
      {doc && (
        <Breadcrumbs items={[
          { label: "Docs", href: "/docs" },
          { label: doc.project, href: `/projects/${encodeURIComponent(doc.project)}` },
          { label: title },
        ]} />
      )}

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
              <ProjectPill name={doc.project} />
            </Link>
            <span className="text-xs text-muted-foreground">{formatDate(doc.updated_at)}</span>
          </div>

          <div
            className={`relative rounded-lg transition-colors ${dragOver ? "ring-2 ring-primary bg-primary/5" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {dragOver && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-primary/10 border-2 border-dashed border-primary">
                <div className="flex items-center gap-2 text-primary font-medium">
                  <Upload className="h-5 w-5" />
                  Drop image to upload
                </div>
              </div>
            )}
            <article ref={articleRef} className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  img: ({ src, alt }) => {
                    const raw = typeof src === "string" ? src : "";
                    const isCairn = raw.startsWith("cairn://attachments/");
                    const resolved = resolveCairnUrl(raw);
                    return (
                      <figure className="my-4">
                        {isCairn ? (
                          <AuthImage
                            src={resolved}
                            alt={alt ?? ""}
                            className="max-w-full rounded-md border border-border"
                          />
                        ) : (
                          <img
                            src={resolved}
                            alt={alt ?? ""}
                            className="max-w-full rounded-md border border-border"
                            loading="lazy"
                          />
                        )}
                        {alt && (
                          <figcaption className="text-xs text-muted-foreground mt-1.5 text-center italic">
                            {alt}
                          </figcaption>
                        )}
                      </figure>
                    );
                  },
                }}
              >{doc.content}</ReactMarkdown>
            </article>
          </div>

          {/* Attachments panel */}
          <div className="border-t border-border pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <ImagePlus className="h-4 w-4" />
                Attachments
                {attachments.length > 0 && (
                  <span className="text-xs text-muted-foreground font-normal">({attachments.length})</span>
                )}
              </h3>
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleUpload(e.target.files);
                      e.target.value = "";
                    }
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                  {uploading ? "Uploading..." : "Upload"}
                </Button>
              </div>
            </div>

            {attachments.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No attachments yet. Upload images or drag and drop onto the document above.
              </p>
            )}

            {attachments.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {attachments.map((att) => (
                  <div
                    key={att.id}
                    className="group relative flex items-center gap-3 rounded-md border border-border p-2.5 hover:bg-accent/50 transition-colors"
                  >
                    <AuthImage
                      src={resolveCairnUrl(att.url)}
                      alt={att.filename}
                      className="h-12 w-12 rounded object-cover border border-border flex-shrink-0"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium truncate" title={att.filename}>{att.filename}</p>
                      <p className="text-xs text-muted-foreground">{formatBytes(att.size_bytes)}</p>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        title="Copy markdown reference"
                        onClick={() => copyMarkdownRef(att)}
                      >
                        <Copy className={`h-3.5 w-3.5 ${copied === att.id ? "text-green-400" : ""}`} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        title="Delete attachment"
                        onClick={() => handleDelete(att.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </PageLayout>
  );
}
