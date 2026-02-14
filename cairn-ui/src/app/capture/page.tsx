"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api, type Project, type IngestResponse } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { AtSign, Check, Hash, Link, Loader2, X, Globe } from "lucide-react";

const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
];

interface SlashCommand {
  label: string;
  description: string;
  action: () => void;
}

/** Extract @mentions, #tags, and URLs from content text. */
function extractInlineEntities(text: string) {
  const mentions = [...new Set(
    Array.from(text.matchAll(/(?:^|\s)@([\w-]+)/g), (m) => m[1]),
  )];
  const hashtags = [...new Set(
    Array.from(text.matchAll(/(?:^|\s)#([\w-]+)/g), (m) => m[1]),
  )];
  const urls = [...new Set(
    Array.from(text.matchAll(/https?:\/\/[^\s)]+/g), (m) => m[0]),
  )];
  return { mentions, hashtags, urls };
}

function CaptureForm() {
  const searchParams = useSearchParams();

  // Form state
  const [content, setContent] = useState(searchParams.get("text") || "");
  const [url, setUrl] = useState(searchParams.get("url") || "");
  const [project, setProject] = useState("");
  const [memoryType, setMemoryType] = useState("note");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");

  // UI state
  const [projects, setProjects] = useState<Project[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Slash command state
  const [slashActive, setSlashActive] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);
  const slashMenuRef = useRef<HTMLDivElement>(null);

  // Pre-fill title from bookmarklet
  const bookmarkletTitle = searchParams.get("title") || "";

  // Load projects
  useEffect(() => {
    api.projects({ limit: "50" }).then((data) => {
      setProjects(data.items);
      const last = localStorage.getItem("cairn-capture-project");
      if (last && data.items.some((p) => p.name === last)) {
        setProject(last);
      } else if (data.items.length > 0) {
        setProject(data.items[0].name);
      }
    });
  }, []);

  // Auto-focus textarea
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Build slash commands list
  const buildSlashCommands = useCallback(
    (filter: string): SlashCommand[] => {
      const cmds: SlashCommand[] = [];
      const f = filter.toLowerCase();

      for (const t of MEMORY_TYPES) {
        if (t.includes(f)) {
          cmds.push({
            label: `/${t}`,
            description: `Set type to ${t}`,
            action: () => setMemoryType(t),
          });
        }
      }

      for (const p of projects) {
        if (p.name.toLowerCase().includes(f)) {
          cmds.push({
            label: `/${p.name}`,
            description: `Set project to ${p.name}`,
            action: () => {
              setProject(p.name);
              localStorage.setItem("cairn-capture-project", p.name);
            },
          });
        }
      }

      return cmds;
    },
    [projects],
  );

  function handleContentChange(value: string) {
    setContent(value);

    // Auto-extract inline entities
    const { mentions, hashtags, urls: detectedUrls } = extractInlineEntities(value);

    // Auto-set project from @mention (first match wins)
    if (mentions.length > 0) {
      const match = projects.find(
        (p) => p.name.toLowerCase() === mentions[0].toLowerCase(),
      );
      if (match && project !== match.name) {
        setProject(match.name);
        localStorage.setItem("cairn-capture-project", match.name);
      }
    }

    // Auto-add #tags (additive — don't remove tags if user deleted the hashtag)
    for (const ht of hashtags) {
      if (!tags.includes(ht)) {
        setTags((prev) => (prev.includes(ht) ? prev : [...prev, ht]));
      }
    }

    // Auto-fill URL field if one is detected and field is empty
    if (detectedUrls.length > 0 && !url) {
      setUrl(detectedUrls[0]);
    }

    // Slash command detection
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPos = textarea.selectionStart;
    const textBeforeCursor = value.slice(0, cursorPos);
    const match = textBeforeCursor.match(/(?:^|\n|\s)\/([\w-]*)$/);

    if (match) {
      const filter = match[1];
      setSlashActive(true);
      setSlashIndex(0);
      setSlashCommands(buildSlashCommands(filter));
    } else {
      setSlashActive(false);
    }
  }

  function executeSlashCommand(cmd: SlashCommand) {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPos = textarea.selectionStart;
    const textBeforeCursor = content.slice(0, cursorPos);
    const textAfterCursor = content.slice(cursorPos);

    const slashStart = textBeforeCursor.lastIndexOf("/");
    if (slashStart >= 0) {
      const newBefore = content.slice(0, slashStart);
      setContent(newBefore + textAfterCursor);

      requestAnimationFrame(() => {
        textarea.selectionStart = textarea.selectionEnd = slashStart;
        textarea.focus();
      });
    }

    cmd.action();
    setSlashActive(false);
  }

  function handleTextareaKeyDown(e: React.KeyboardEvent) {
    if (slashActive && slashCommands.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((i) => Math.min(i + 1, slashCommands.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        executeSlashCommand(slashCommands[slashIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashActive(false);
        return;
      }
    }

    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleTagKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const tag = tagInput.trim().replace(/,/g, "");
      if (tag && !tags.includes(tag)) {
        setTags([...tags, tag]);
      }
      setTagInput("");
    }
    if (e.key === "Backspace" && !tagInput && tags.length > 0) {
      setTags(tags.slice(0, -1));
    }
  }

  function removeTag(tag: string) {
    setTags(tags.filter((t) => t !== tag));
  }

  async function handleSubmit() {
    if (!content && !url) return;
    if (!project) return;

    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.ingest({
        content: content || undefined,
        url: url || undefined,
        project,
        tags: tags.length > 0 ? tags : undefined,
        hint: "memory",
        memory_type: memoryType,
        title: bookmarkletTitle || undefined,
      });
      setResult(res);

      if (res.status === "ingested") {
        const ids = res.memory_ids?.map((id) => `#${id}`).join(", ") || "";
        toast.success(`Captured ${ids}`, { description: `${project} / ${memoryType}` });
        setContent("");
        setUrl("");
        setTags([]);
        setTagInput("");
        textareaRef.current?.focus();
      } else if (res.status === "duplicate") {
        toast.info("Duplicate — already captured");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Capture failed";
      toast.error("Capture failed", { description: msg });
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Main textarea */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          placeholder="What are you capturing? (/ commands, @project, #tags)"
          value={content}
          onChange={(e) => handleContentChange(e.target.value)}
          onKeyDown={handleTextareaKeyDown}
          rows={8}
          className={cn(
            "w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none resize-y min-h-[120px]",
            "border-input placeholder:text-muted-foreground",
            "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          )}
        />

        {/* Slash command menu */}
        {slashActive && slashCommands.length > 0 && (
          <div
            ref={slashMenuRef}
            className="absolute left-0 top-full mt-1 z-50 w-64 rounded-md border bg-popover p-1 shadow-md"
          >
            {slashCommands.slice(0, 8).map((cmd, i) => (
              <button
                key={cmd.label}
                type="button"
                className={cn(
                  "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm",
                  i === slashIndex
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
                onMouseDown={(e) => {
                  e.preventDefault();
                  executeSlashCommand(cmd);
                }}
                onMouseEnter={() => setSlashIndex(i)}
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {cmd.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  {cmd.description}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Inline entity hints */}
      {content && (() => {
        const { mentions, hashtags, urls: detected } = extractInlineEntities(content);
        if (mentions.length === 0 && hashtags.length === 0 && detected.length === 0) return null;
        return (
          <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground -mt-2">
            {mentions.map((m) => (
              <span key={m} className="flex items-center gap-1">
                <AtSign className="h-3 w-3" />
                <span className={projects.some((p) => p.name.toLowerCase() === m.toLowerCase()) ? "text-primary" : "text-yellow-500"}>
                  {m}
                </span>
              </span>
            ))}
            {hashtags.map((t) => (
              <span key={t} className="flex items-center gap-1">
                <Hash className="h-3 w-3" />
                {t}
              </span>
            ))}
            {detected.map((u) => (
              <span key={u} className="flex items-center gap-1 truncate max-w-[200px]">
                <Globe className="h-3 w-3" />
                {u}
              </span>
            ))}
          </div>
        );
      })()}

      {/* URL field */}
      <div className="relative">
        <Link className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="URL (optional — paste a link to capture its content)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Project + Type row */}
      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex gap-1 flex-wrap">
          {projects.map((p) => (
            <Button
              key={p.id}
              type="button"
              variant={project === p.name ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setProject(p.name);
                localStorage.setItem("cairn-capture-project", p.name);
              }}
            >
              {p.name}
            </Button>
          ))}
        </div>

        <div className="h-4 w-px bg-border" />

        <select
          value={memoryType}
          onChange={(e) => setMemoryType(e.target.value)}
          className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
        >
          {MEMORY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* Tags */}
      <div className="flex items-center gap-2 flex-wrap rounded-md border border-input px-3 py-1.5 min-h-[36px]">
        {tags.map((tag) => (
          <Badge
            key={tag}
            variant="secondary"
            className="gap-1 cursor-pointer"
            onClick={() => removeTag(tag)}
          >
            {tag}
            <X className="h-3 w-3" />
          </Badge>
        ))}
        <input
          ref={tagInputRef}
          placeholder={tags.length === 0 ? "Tags (type + Enter)" : ""}
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={handleTagKeyDown}
          className="flex-1 min-w-[80px] bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {project && (
            <>
              <span className="font-mono">{project}</span>
              {" / "}
              <span className="font-mono">{memoryType}</span>
            </>
          )}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setContent("");
              setUrl("");
              setTags([]);
              setTagInput("");
              setResult(null);
              setError(null);
              textareaRef.current?.focus();
            }}
          >
            Clear
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting || (!content && !url) || !project}
          >
            {submitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Capturing...
              </>
            ) : (
              "Capture \u2318\u21B5"
            )}
          </Button>
        </div>
      </div>

      {/* Result toast */}
      {result && (
        <Card
          className={cn(
            "border-l-4",
            result.status === "ingested"
              ? "border-l-green-500"
              : "border-l-yellow-500",
          )}
        >
          <CardContent className="flex items-center gap-2 p-3">
            <Check className="h-4 w-4 text-green-500" />
            {result.status === "ingested" ? (
              <span className="text-sm">
                Captured{" "}
                {result.memory_ids && result.memory_ids.length > 0 && (
                  <>
                    as{" "}
                    {result.memory_ids.map((id) => (
                      <a
                        key={id}
                        href={`/memories/${id}`}
                        className="font-mono text-primary hover:underline"
                      >
                        #{id}
                      </a>
                    ))}
                  </>
                )}
                {result.chunk_count && result.chunk_count > 1 && (
                  <span className="text-muted-foreground">
                    {" "}({result.chunk_count} chunks)
                  </span>
                )}
              </span>
            ) : (
              <span className="text-sm text-yellow-600">
                Duplicate — already captured
              </span>
            )}
          </CardContent>
        </Card>
      )}

      {error && (
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="p-3">
            <span className="text-sm text-red-500">{error}</span>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CaptureExtras() {
  const [showExtras, setShowExtras] = useState(false);

  return (
    <div className="space-y-2 pt-4 border-t border-border">
      <button
        type="button"
        onClick={() => setShowExtras(!showExtras)}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {showExtras ? "Hide" : "Show"} capture shortcuts
      </button>

      {showExtras && (
        <div className="space-y-4 text-sm">
          <Card>
            <CardContent className="p-4 space-y-2">
              <h3 className="font-medium">Browser Bookmarklet</h3>
              <p className="text-xs text-muted-foreground">
                Drag this link to your bookmarks bar. Click it on any page to
                capture the URL + selected text.
              </p>
              <a
                href={`javascript:void(window.open('${typeof window !== 'undefined' ? window.location.origin : ''}/capture?url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title)+'&text='+encodeURIComponent(window.getSelection().toString()),'_blank','width=600,height=600'))`}
                className="inline-block px-3 py-1.5 rounded-md border bg-muted text-xs font-mono hover:bg-accent transition-colors"
                onClick={(e) => e.preventDefault()}
              >
                Capture to Cairn
              </a>
              <p className="text-xs text-muted-foreground">
                (Drag it — don&apos;t click.)
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 space-y-2">
              <h3 className="font-medium">iOS Shortcut</h3>
              <p className="text-xs text-muted-foreground">
                Use the share sheet on any page or text to send it to Cairn.
                Create an Apple Shortcut that POSTs to:
              </p>
              <code className="block text-xs bg-muted px-2 py-1 rounded">
                POST https://your-cairn-host/api/ingest
              </code>
              <p className="text-xs text-muted-foreground">
                Body: <code>{`{content, url, project, source: "ios-shortcut"}`}</code>
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function CapturePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Capture</h1>
      <Suspense>
        <CaptureForm />
      </Suspense>
      <CaptureExtras />
    </div>
  );
}
