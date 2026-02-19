"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  api,
  type WorkspaceHealth,
  type WorkspaceSession,
  type WorkspaceMessage,
  type WorkspaceAgent,
  type WorkspaceBackendInfo,
  type Project,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Boxes,
  Plus,
  Trash2,
  Send,
  Bot,
  User,
  Loader2,
  Wifi,
  WifiOff,
  Square,
  ChevronDown,
  ChevronRight,
  FileCode,
  Wrench,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Not configured state
// ---------------------------------------------------------------------------
function NotConfiguredState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto gap-6 p-8">
      <div className="rounded-full bg-muted p-4">
        <Boxes className="h-8 w-8 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-xl font-semibold mb-2">Workspace not configured</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Configure an agent backend to enable the workspace.
        </p>
      </div>
      <div className="text-left w-full space-y-4">
        <div>
          <h3 className="text-sm font-medium mb-1">OpenCode (OSS models)</h3>
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto">
{`# Start OpenCode in headless mode
opencode serve --hostname 0.0.0.0 --port 4096

# Set Cairn env vars
CAIRN_OPENCODE_URL=http://localhost:4096
CAIRN_OPENCODE_PASSWORD=your-secret`}
          </pre>
        </div>
        <div>
          <h3 className="text-sm font-medium mb-1">Claude Code (Opus / Sonnet)</h3>
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto">
{`# Install Claude Code CLI
# https://docs.anthropic.com/en/docs/claude-code

# Set Cairn env vars
CAIRN_CLAUDE_CODE_ENABLED=true
CAIRN_CLAUDE_CODE_WORKING_DIR=/path/to/project`}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session sidebar
// ---------------------------------------------------------------------------
function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  health,
}: {
  sessions: WorkspaceSession[];
  activeId: string | null;
  onSelect: (session: WorkspaceSession) => void;
  onCreate: () => void;
  onDelete: (sessionId: string) => void;
  health: WorkspaceHealth | null;
}) {
  return (
    <div className="w-64 shrink-0 border-r border-border flex flex-col bg-card">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Sessions
        </span>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onCreate}>
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
        {sessions.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            No sessions yet
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className={cn(
              "group flex items-center gap-2 rounded-md px-2.5 py-2 text-sm cursor-pointer transition-colors",
              activeId === s.session_id
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground"
            )}
            onClick={() => onSelect(s)}
          >
            <Bot className="h-3.5 w-3.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="truncate font-medium text-xs">
                {s.task || s.title || "Untitled"}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[10px] opacity-60">{s.agent}</span>
                <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5">
                  {s.project}
                </Badge>
                {s.backend && (
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[9px] px-1 py-0 h-3.5",
                      s.backend === "claude_code" ? "border-violet-500/50 text-violet-500" : "border-emerald-500/50 text-emerald-500"
                    )}
                  >
                    {s.backend === "claude_code" ? "CC" : "OC"}
                  </Badge>
                )}
              </div>
            </div>
            <button
              className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-destructive/20"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.session_id);
              }}
            >
              <Trash2 className="h-3 w-3 text-destructive" />
            </button>
          </div>
        ))}
      </div>
      <div className="px-3 py-2 border-t border-border space-y-1">
        {health?.status === "not_configured" ? (
          <div className="flex items-center gap-1.5">
            <WifiOff className="h-3 w-3 text-muted-foreground" />
            <span className="text-[10px] text-muted-foreground">Not configured</span>
          </div>
        ) : health?.backends ? (
          Object.entries(health.backends).map(([name, info]) => (
            <div key={name} className="flex items-center gap-1.5">
              {info.status === "healthy" ? (
                <Wifi className="h-3 w-3 text-green-500" />
              ) : (
                <WifiOff className="h-3 w-3 text-red-500" />
              )}
              <span className={cn("text-[10px]", info.status === "healthy" ? "text-green-500" : "text-red-500")}>
                {name === "claude_code" ? "Claude Code" : "OpenCode"} {info.version || ""}
              </span>
            </div>
          ))
        ) : health?.status === "healthy" ? (
          <div className="flex items-center gap-1.5">
            <Wifi className="h-3 w-3 text-green-500" />
            <span className="text-[10px] text-green-500">Connected</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <WifiOff className="h-3 w-3 text-red-500" />
            <span className="text-[10px] text-red-500">Disconnected</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create session dialog
// ---------------------------------------------------------------------------
function CreateSessionDialog({
  open,
  onClose,
  onCreated,
  agents,
  backends,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (session: WorkspaceSession) => void;
  agents: WorkspaceAgent[];
  backends: WorkspaceBackendInfo[];
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState("");
  const [task, setTask] = useState("");
  const [agent, setAgent] = useState("");
  const [selectedBackend, setSelectedBackend] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [contextMode, setContextMode] = useState<"focused" | "full">("focused");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const showBackendSelector = backends.length > 1;

  useEffect(() => {
    if (open) {
      api.projects({ limit: "100" }).then((r) => setProjects(r.items)).catch(() => {});
    }
  }, [open]);

  const showModelSelector = selectedBackend === "claude_code";

  const reset = () => {
    setProject("");
    setTask("");
    setAgent("");
    setSelectedBackend("");
    setSelectedModel("");
    setContextMode("focused");
    setError("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project) {
      setError("Project is required");
      return;
    }
    setError("");
    setSaving(true);
    try {
      const session = await api.workspaceCreateSession({
        project,
        task: task || undefined,
        agent: agent || undefined,
        context_mode: contextMode,
        backend: selectedBackend || undefined,
        model: selectedModel || undefined,
      });
      if (session.error) {
        setError(session.error);
        return;
      }
      reset();
      onCreated(session);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setSaving(false);
    }
  };

  const backendLabel = (name: string) => {
    if (name === "claude_code") return "Claude Code";
    if (name === "opencode") return "OpenCode (OSS models)";
    return name;
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Workspace Session</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Project</label>
            <SingleSelect
              options={projects
                .filter((p) => p.name !== "__global__")
                .map((p) => ({ value: p.name, label: p.name }))}
              value={project}
              onValueChange={setProject}
              placeholder="Select project..."
              className="w-full h-9"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">
              Task description
            </label>
            <textarea
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs min-h-[80px] resize-y"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="What should the agent work on?"
            />
          </div>

          {showBackendSelector && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">Backend</label>
              <SingleSelect
                options={[
                  { value: "", label: "Default" },
                  ...backends
                    .filter((b) => b.status === "healthy")
                    .map((b) => ({
                      value: b.name,
                      label: `${backendLabel(b.name)}${b.is_default ? " (default)" : ""}`,
                    })),
                ]}
                value={selectedBackend}
                onValueChange={(v) => {
                  setSelectedBackend(v);
                  if (v !== "claude_code") setSelectedModel("");
                }}
                className="w-full h-9"
              />
            </div>
          )}

          {showModelSelector && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">Model</label>
              <SingleSelect
                options={[
                  { value: "", label: "Opus 4.6 (default)" },
                  { value: "claude-sonnet-4-6", label: "Sonnet 4.6 (faster, saves usage)" },
                ]}
                value={selectedModel}
                onValueChange={setSelectedModel}
                className="w-full h-9"
              />
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-muted-foreground">Agent</label>
            <SingleSelect
              options={[
                { value: "", label: "Default (cairn-build)" },
                ...agents.map((a) => ({
                  value: a.id,
                  label: `${a.name || a.id}${a.model ? ` (${a.model})` : ""}`,
                })),
              ]}
              value={agent}
              onValueChange={setAgent}
              className="w-full h-9"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">Context</label>
            <SingleSelect
              options={[
                { value: "focused", label: "Focused — project rules + task context only" },
                { value: "full", label: "Full — grimoire, trail, tasks, everything" },
              ]}
              value={contextMode}
              onValueChange={(v) => setContextMode(v as "focused" | "full")}
              className="w-full h-9"
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
              Create Session
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------
function MessageBubble({ msg }: { msg: WorkspaceMessage }) {
  const isUser = msg.role === "user";
  const isContext = isUser && msg.parts.some(
    (p) => p.type === "text" && typeof p.text === "string" && p.text.startsWith("[CAIRN CONTEXT]")
  );
  const [contextExpanded, setContextExpanded] = useState(false);

  // Separate text parts from tool parts
  const textParts = msg.parts.filter((p) => p.type === "text");
  const toolParts = msg.parts.filter((p) => p.type === "tool-invocation" || p.type === "tool-result");

  // Context injection message — show as collapsed block
  if (isContext) {
    return (
      <div className="flex gap-3 justify-start">
        <div className="mt-1 shrink-0">
          <Boxes className="h-4 w-4 text-muted-foreground/60" />
        </div>
        <button
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
          onClick={() => setContextExpanded(!contextExpanded)}
        >
          {contextExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          Cairn context injected
        </button>
        {contextExpanded && (
          <pre className="mt-1 text-[10px] bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all text-muted-foreground max-h-60 overflow-y-auto">
            {textParts.map((p) => p.text).join("\n")}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 shrink-0">
          <Bot className="h-5 w-5 text-muted-foreground" />
        </div>
      )}
      <div
        className={cn(
          "rounded-lg px-3 py-2 text-sm max-w-[80%]",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        {/* Tool calls */}
        {toolParts.length > 0 && (
          <div className="space-y-1 mb-2 pb-2 border-b border-border/50">
            {toolParts.map((tp, j) => (
              <details key={j} className="group">
                <summary className="cursor-pointer text-xs text-muted-foreground flex items-center gap-1.5 hover:text-foreground transition-colors">
                  <Wrench className="h-3 w-3 shrink-0" />
                  <span className="font-medium">
                    {String(tp.toolName || tp.name || "tool")}
                  </span>
                </summary>
                <pre className="mt-1 text-[10px] bg-background/50 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all text-muted-foreground">
                  {tp.type === "tool-invocation"
                    ? JSON.stringify(tp.args ?? tp.input, null, 2)
                    : JSON.stringify(tp.result ?? tp.output, null, 2)}
                </pre>
              </details>
            ))}
          </div>
        )}
        {/* Text content */}
        <div className="whitespace-pre-wrap">
          {textParts.map((p) => p.text).join("\n")}
        </div>
      </div>
      {isUser && (
        <div className="mt-1 shrink-0">
          <User className="h-5 w-5 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session view — status bar + messages + input
// ---------------------------------------------------------------------------
function SessionView({
  session,
  onAbort,
  onViewDiff,
}: {
  session: WorkspaceSession;
  onAbort: () => void;
  onViewDiff: () => void;
}) {
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load messages when session changes
  useEffect(() => {
    setLoadingMessages(true);
    api
      .workspaceMessages(session.session_id)
      .then((msgs) => setMessages(msgs))
      .catch(() => setMessages([]))
      .finally(() => setLoadingMessages(false));
  }, [session.session_id]);

  // Auto-scroll
  useEffect(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }, [messages]);

  // Focus input
  useEffect(() => {
    if (!loadingMessages) inputRef.current?.focus();
  }, [loadingMessages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    // Optimistic add user message
    const optimistic: WorkspaceMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      parts: [{ type: "text", text }],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    setSending(true);

    try {
      const result = await api.workspaceSendMessage(session.session_id, { text });
      if (result.response) {
        const assistantMsg: WorkspaceMessage = {
          id: `resp-${Date.now()}`,
          role: "assistant",
          parts: [{ type: "text", text: result.response }],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }
    } catch (err) {
      const errorMsg: WorkspaceMessage = {
        id: `err-${Date.now()}`,
        role: "assistant",
        parts: [
          {
            type: "text",
            text: `Error: ${err instanceof Error ? err.message : "Failed to send message"}`,
          },
        ],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setSending(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Status bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-card text-xs shrink-0">
        <span className="font-medium truncate">
          {session.task || session.title || "Untitled"}
        </span>
        <Badge variant="outline" className="text-[10px] shrink-0">
          {session.agent}
        </Badge>
        <Badge variant="outline" className="text-[10px] shrink-0">
          {session.project}
        </Badge>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={onViewDiff}
        >
          <FileCode className="h-3 w-3 mr-1" />
          Diff
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs text-destructive hover:text-destructive"
          onClick={onAbort}
        >
          <Square className="h-3 w-3 mr-1" />
          Abort
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loadingMessages ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Bot className="mx-auto mb-3 h-10 w-10 opacity-30" />
              <p className="text-sm">Session ready.</p>
              <p className="text-xs mt-1 opacity-60">
                Send a message to start working with the agent.
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            {sending && (
              <div className="flex gap-3 justify-start">
                <div className="mt-1 shrink-0">
                  <Bot className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="bg-muted rounded-lg px-3 py-2">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t px-4 py-3">
        <div className="mx-auto max-w-3xl flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Send a message to the agent..."
            rows={1}
            className={cn(
              "flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm",
              "ring-offset-background placeholder:text-muted-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
            disabled={sending}
          />
          <Button size="icon" onClick={handleSend} disabled={sending || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Diff viewer dialog
// ---------------------------------------------------------------------------
function DiffDialog({
  open,
  onClose,
  sessionId,
}: {
  open: boolean;
  onClose: () => void;
  sessionId: string;
}) {
  const [diffs, setDiffs] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (open) {
      setLoading(true);
      api
        .workspaceDiff(sessionId)
        .then(setDiffs)
        .catch(() => setDiffs([]))
        .finally(() => setLoading(false));
    }
  }, [open, sessionId]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Session Diffs</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : diffs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            No file changes in this session.
          </p>
        ) : (
          <div className="space-y-3">
            {diffs.map((d, i) => (
              <div key={i} className="rounded border border-border">
                <div className="px-3 py-1.5 bg-muted text-xs font-mono font-medium border-b border-border">
                  {String(d.path || d.file || `File ${i + 1}`)}
                </div>
                <pre className="px-3 py-2 text-[11px] font-mono overflow-x-auto whitespace-pre-wrap">
                  {String(d.content || d.diff || d.patch || JSON.stringify(d, null, 2))}
                </pre>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// No session selected state
// ---------------------------------------------------------------------------
function NoSessionSelected() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-3">
      <Boxes className="h-10 w-10 text-muted-foreground/30" />
      <p className="text-sm text-muted-foreground">
        Select a session or create a new one
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function WorkspacePage() {
  const [health, setHealth] = useState<WorkspaceHealth | null>(null);
  const [sessions, setSessions] = useState<WorkspaceSession[]>([]);
  const [agents, setAgents] = useState<WorkspaceAgent[]>([]);
  const [backends, setBackends] = useState<WorkspaceBackendInfo[]>([]);
  const [activeSession, setActiveSession] = useState<WorkspaceSession | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [diffDialogOpen, setDiffDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadHealth = useCallback(async () => {
    try {
      const h = await api.workspaceHealth();
      setHealth(h);
      return h;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check workspace health");
      return null;
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.workspaceSessions();
      setSessions(list);
    } catch {
      // May fail if not configured
    }
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      const list = await api.workspaceAgents();
      setAgents(list);
    } catch {
      // May fail if not configured
    }
  }, []);

  const loadBackends = useCallback(async () => {
    try {
      const list = await api.workspaceBackends();
      setBackends(list);
    } catch {
      // May fail if not configured
    }
  }, []);

  useEffect(() => {
    async function init() {
      const h = await loadHealth();
      if (h && h.status !== "not_configured") {
        await Promise.all([loadSessions(), loadAgents(), loadBackends()]);
      }
      setLoading(false);
    }
    init();
  }, [loadHealth, loadSessions, loadAgents, loadBackends]);

  const handleDelete = async (sessionId: string) => {
    try {
      await api.workspaceDeleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      if (activeSession?.session_id === sessionId) setActiveSession(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete session");
    }
  };

  const handleAbort = async () => {
    if (!activeSession) return;
    try {
      await api.workspaceAbortSession(activeSession.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to abort session");
    }
  };

  const handleCreated = (session: WorkspaceSession) => {
    setSessions((prev) => [session, ...prev]);
    setActiveSession(session);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-8rem)]">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !health) {
    return (
      <div className="p-4 md:p-6">
        <ErrorState message={error} />
      </div>
    );
  }

  if (!health || health.status === "not_configured") {
    return <NotConfiguredState />;
  }

  return (
    <div
      className="flex -m-4 md:-m-6"
      style={{ height: "calc(100vh - var(--removed, 0px))" }}
    >
      <SessionSidebar
        sessions={sessions}
        activeId={activeSession?.session_id ?? null}
        onSelect={setActiveSession}
        onCreate={() => setDialogOpen(true)}
        onDelete={handleDelete}
        health={health}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        {activeSession ? (
          <SessionView
            key={activeSession.session_id}
            session={activeSession}
            onAbort={handleAbort}
            onViewDiff={() => setDiffDialogOpen(true)}
          />
        ) : (
          <NoSessionSelected />
        )}
      </div>

      <CreateSessionDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
        agents={agents}
        backends={backends}
      />

      {activeSession && (
        <DiffDialog
          open={diffDialogOpen}
          onClose={() => setDiffDialogOpen(false)}
          sessionId={activeSession.session_id}
        />
      )}
    </div>
  );
}
