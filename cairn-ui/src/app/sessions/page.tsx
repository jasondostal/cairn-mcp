"use client";

import { useState, useEffect, useCallback } from "react";
import { api, SessionInfo, SessionEvent } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Radio,
  ChevronRight,
  ArrowLeft,
  Wrench,
  Play,
  Square,
  Loader2,
  FileText,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { PageLayout } from "@/components/page-layout";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(dateStr).getTime()) / 1000
  );
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function eventIcon(type: string) {
  if (type === "tool_use") return <Wrench className="h-3 w-3" />;
  if (type === "session_start") return <Play className="h-3 w-3" />;
  if (type === "session_end") return <Square className="h-3 w-3" />;
  return <FileText className="h-3 w-3" />;
}

function toolInputPreview(input: Record<string, unknown> | undefined): string {
  if (!input) return "";
  if (input.command) return String(input.command).slice(0, 80);
  if (input.file_path) return String(input.file_path);
  if (input.pattern) return `/${input.pattern}/`;
  if (input.query) return `"${String(input.query).slice(0, 60)}"`;
  if (input.content) return String(input.content).slice(0, 60) + "...";
  const keys = Object.keys(input);
  if (keys.length === 0) return "";
  return keys.slice(0, 3).join(", ");
}

// -- Session List --

function SessionList({
  sessions,
  onSelect,
  loading,
  error,
  onRefresh,
}: {
  sessions: SessionInfo[];
  onSelect: (s: SessionInfo) => void;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  return (
    <>
      {error && <ErrorState message="Failed to load sessions" detail={error} />}

      {!error && sessions.length === 0 && !loading && (
        <div className="text-center py-12 text-muted-foreground">
          <Radio className="mx-auto mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">No sessions yet.</p>
          <p className="text-xs mt-1 opacity-60">
            Sessions appear when Claude Code hooks ship events.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {sessions.map((s) => (
          <button
            key={s.session_name}
            onClick={() => onSelect(s)}
            className={cn(
              "w-full text-left rounded-lg border px-4 py-3 transition-colors",
              "hover:bg-muted/50",
              s.is_active && "border-green-500/50 bg-green-500/5"
            )}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                {s.is_active ? (
                  <span className="relative flex h-2.5 w-2.5 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
                  </span>
                ) : (
                  <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30 shrink-0" />
                )}
                <span className="font-mono text-sm truncate">
                  {s.session_name}
                </span>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            </div>
            <div className="flex items-center gap-4 mt-1.5 text-xs text-muted-foreground">
              <span>{s.project}</span>
              <span>{s.event_count} events</span>
              {s.started_at && <span>{timeAgo(s.started_at)}</span>}
            </div>
          </button>
        ))}
      </div>
    </>
  );
}

// -- Session Detail (Event Stream) --

function SessionDetail({
  session,
  onBack,
}: {
  session: SessionInfo;
  onBack: () => void;
}) {
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(session.is_active);

  const fetchEvents = useCallback(async () => {
    try {
      const result = await api.sessionEvents(session.session_name);
      setEvents(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
    } finally {
      setLoading(false);
    }
  }, [session.session_name]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchEvents, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchEvents]);

  const toolEvents = events.filter((e) => e.event_type === "tool_use");

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold truncate font-mono">
              {session.session_name}
            </h2>
            {session.is_active && (
              <span className="text-[10px] font-medium uppercase tracking-wider text-green-500 bg-green-500/10 px-1.5 py-0.5 rounded">
                live
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
            <span>{session.project}</span>
            <span>{events.length} events</span>
            <span>{toolEvents.length} tool calls</span>
          </div>
        </div>
        {session.is_active && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className="text-xs"
          >
            {autoRefresh ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin mr-1" /> Auto
              </>
            ) : (
              "Auto off"
            )}
          </Button>
        )}
      </div>

      {/* Error banner */}
      {error && !loading && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive mb-4">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={fetchEvents} className="ml-auto text-xs">
            Retry
          </Button>
        </div>
      )}

      {/* Event Stream */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : events.length === 0 && !error ? (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No events yet.
        </div>
      ) : (
        <div className="space-y-0.5">
          {events.map((evt) => {
            const payload = evt.payload || {};
            const toolInput = (payload.tool_input ?? payload.input) as Record<string, unknown> | undefined;
            const toolResponse = (payload.tool_response ?? payload.response) as string | undefined;
            const reason = payload.reason as string | undefined;

            return (
              <div
                key={evt.id}
                className={cn(
                  "flex items-start gap-2 rounded px-2 py-1.5 text-xs",
                  "hover:bg-muted/50 transition-colors",
                  evt.event_type === "session_start" && "bg-blue-500/5",
                  evt.event_type === "session_end" && "bg-orange-500/5"
                )}
              >
                <div className="mt-0.5 text-muted-foreground shrink-0">
                  {eventIcon(evt.event_type)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {evt.tool_name || evt.event_type}
                    </span>
                    {evt.event_type === "session_end" && reason && (
                      <span className="text-muted-foreground">({reason})</span>
                    )}
                    <span className="text-muted-foreground ml-auto shrink-0">
                      {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ""}
                    </span>
                  </div>
                  {toolInput && (
                    <div className="text-muted-foreground truncate mt-0.5 font-mono text-[11px]">
                      {toolInputPreview(toolInput)}
                    </div>
                  )}
                  {toolResponse && (
                    <details className="mt-0.5 group">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors">
                        response ({toolResponse.length} chars)
                      </summary>
                      <pre className="mt-1 text-[10px] bg-background/50 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all text-muted-foreground max-h-32 overflow-y-auto">
                        {toolResponse}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// -- Page --

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [selected, setSelected] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.sessions({ limit: "30" });
      setSessions(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Auto-refresh session list every 30s
  useEffect(() => {
    const interval = setInterval(fetchSessions, 30000);
    return () => clearInterval(interval);
  }, [fetchSessions]);

  return (
    <PageLayout
      title="Sessions"
      titleExtra={
        !selected && (
          <Button variant="ghost" size="icon" onClick={fetchSessions} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </Button>
        )
      }
    >
      {selected ? (
        <SessionDetail
          session={selected}
          onBack={() => setSelected(null)}
        />
      ) : (
        <SessionList
          sessions={sessions}
          onSelect={setSelected}
          loading={loading}
          error={error}
          onRefresh={fetchSessions}
        />
      )}
    </PageLayout>
  );
}
