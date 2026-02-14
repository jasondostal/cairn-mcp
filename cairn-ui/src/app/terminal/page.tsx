"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { api, type TerminalConfig, type TerminalHost } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Terminal as TerminalIcon,
  Plus,
  Trash2,
  Server,
  Wifi,
  WifiOff,
  Loader2,
  Info,
  X,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Disabled state — setup instructions
// ---------------------------------------------------------------------------
function DisabledState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto gap-6 p-8">
      <div className="rounded-full bg-muted p-4">
        <TerminalIcon className="h-8 w-8 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-xl font-semibold mb-2">Terminal not configured</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Enable the web terminal by setting the <code className="text-xs bg-muted px-1.5 py-0.5 rounded">CAIRN_TERMINAL_BACKEND</code> environment variable.
        </p>
      </div>
      <div className="text-left w-full space-y-4">
        <div>
          <h3 className="text-sm font-medium mb-1">Quick start (ttyd)</h3>
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto">
{`# Run a ttyd container
docker run -d --name ttyd -p 7681:7681 tsl0922/ttyd bash

# Set env var
CAIRN_TERMINAL_BACKEND=ttyd`}
          </pre>
        </div>
        <div>
          <h3 className="text-sm font-medium mb-1">Full setup (native SSH)</h3>
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto">
{`# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set env vars
CAIRN_TERMINAL_BACKEND=native
CAIRN_SSH_ENCRYPTION_KEY=<key>`}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Host sidebar
// ---------------------------------------------------------------------------
function HostSidebar({
  hosts,
  activeId,
  onSelect,
  onAdd,
  onEdit,
  onDelete,
  backend,
}: {
  hosts: TerminalHost[];
  activeId: number | null;
  onSelect: (host: TerminalHost) => void;
  onAdd: () => void;
  onEdit: (host: TerminalHost) => void;
  onDelete: (id: number) => void;
  backend: string;
}) {
  return (
    <div className="w-56 shrink-0 border-r border-border flex flex-col bg-card">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Hosts</span>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onAdd}>
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
        {hosts.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">No hosts yet</p>
        )}
        {hosts.map((host) => (
          <div
            key={host.id}
            className={cn(
              "group flex items-center gap-2 rounded-md px-2.5 py-2 text-sm cursor-pointer transition-colors",
              activeId === host.id
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground"
            )}
            onClick={() => onSelect(host)}
          >
            <Server className="h-3.5 w-3.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="truncate font-medium text-xs">{host.name}</div>
              <div className="truncate text-[10px] opacity-60">
                {backend === "ttyd" ? (host.ttyd_url || host.hostname) : `${host.hostname}:${host.port}`}
              </div>
            </div>
            <button
              className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-accent"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(host);
              }}
            >
              <Pencil className="h-3 w-3 text-muted-foreground" />
            </button>
            <button
              className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-destructive/20"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(host.id);
              }}
            >
              <Trash2 className="h-3 w-3 text-destructive" />
            </button>
          </div>
        ))}
      </div>
      <div className="px-3 py-2 border-t border-border">
        <Badge variant="outline" className="text-[10px]">
          {backend}
        </Badge>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Host Dialog
// ---------------------------------------------------------------------------
function HostDialog({
  open,
  onClose,
  onSaved,
  backend,
  editHost,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  backend: string;
  editHost?: TerminalHost | null;
}) {
  const isEdit = !!editHost;
  const [name, setName] = useState("");
  const [hostname, setHostname] = useState("");
  const [port, setPort] = useState("22");
  const [username, setUsername] = useState("");
  const [credential, setCredential] = useState("");
  const [authMethod, setAuthMethod] = useState("password");
  const [ttydUrl, setTtydUrl] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const reset = () => {
    setName(""); setHostname(""); setPort("22"); setUsername("");
    setCredential(""); setAuthMethod("password"); setTtydUrl("");
    setDescription(""); setError("");
  };

  // Pre-fill when editing
  useEffect(() => {
    if (editHost) {
      setName(editHost.name || "");
      setHostname(editHost.hostname || "");
      setPort(String(editHost.port || 22));
      setUsername(editHost.username || "");
      setCredential("");  // Never pre-fill credentials
      setAuthMethod(editHost.auth_method || "password");
      setTtydUrl(editHost.ttyd_url || "");
      setDescription(editHost.description || "");
      setError("");
    } else {
      reset();
    }
  }, [editHost]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (isEdit) {
        const body: Record<string, unknown> = {
          name, hostname, port: parseInt(port, 10),
          username: username || undefined,
          auth_method: authMethod,
          description: description || undefined,
        };
        if (credential) body.credential = credential;
        if (ttydUrl) body.ttyd_url = ttydUrl;
        await api.terminalUpdateHost(editHost!.id, body);
      } else {
        await api.terminalCreateHost({
          name, hostname, port: parseInt(port, 10),
          username: username || undefined,
          credential: credential || undefined,
          auth_method: authMethod,
          ttyd_url: ttydUrl || undefined,
          description: description || undefined,
        });
      }
      reset();
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${isEdit ? "update" : "create"} host`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Host" : "Add Host"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-server" required />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Hostname</label>
              <Input value={hostname} onChange={(e) => setHostname(e.target.value)} placeholder="192.168.1.10" required />
            </div>
          </div>

          {backend === "native" && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Port</label>
                  <Input type="number" value={port} onChange={(e) => setPort(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Username</label>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="root" required />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Auth</label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
                    value={authMethod}
                    onChange={(e) => setAuthMethod(e.target.value)}
                  >
                    <option value="password">Password</option>
                    <option value="key">SSH Key</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  {authMethod === "key" ? "Private Key" : "Password"}
                  {isEdit && <span className="text-muted-foreground/60 ml-1">(leave blank to keep existing)</span>}
                </label>
                {authMethod === "key" ? (
                  <textarea
                    className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs font-mono shadow-xs min-h-[100px] resize-y"
                    value={credential}
                    onChange={(e) => setCredential(e.target.value)}
                    placeholder={isEdit ? "Leave blank to keep existing key" : "-----BEGIN OPENSSH PRIVATE KEY-----"}
                    required={!isEdit}
                  />
                ) : (
                  <Input
                    type="password"
                    value={credential}
                    onChange={(e) => setCredential(e.target.value)}
                    placeholder={isEdit ? "Leave blank to keep existing" : ""}
                    required={!isEdit}
                  />
                )}
              </div>
            </>
          )}

          {backend === "ttyd" && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">ttyd URL</label>
              <Input
                value={ttydUrl}
                onChange={(e) => setTtydUrl(e.target.value)}
                placeholder="http://ttyd:7681"
                required
              />
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-muted-foreground">Description (optional)</label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Production server" />
          </div>

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
              {isEdit ? "Save" : "Add Host"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Native terminal (xterm.js + WebSocket)
// ---------------------------------------------------------------------------
function NativeTerminal({ host }: { host: TerminalHost }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const termRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let terminal: any = null;
    let fitAddon: any = null;
    let ws: WebSocket | null = null;
    let disposed = false;

    async function init() {
      // Dynamic imports — xterm packages
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      if (disposed || !containerRef.current) return;

      terminal = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        theme: {
          background: "#0a0a0a",
          foreground: "#e4e4e7",
          cursor: "#e4e4e7",
          selectionBackground: "#3f3f46",
        },
      });
      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);
      terminal.open(containerRef.current);
      fitAddon.fit();
      termRef.current = terminal;

      terminal.write(`Connecting to ${host.hostname}...\r\n`);

      // Determine WebSocket URL
      const wsEnv = (typeof window !== "undefined" && (window as any).__NEXT_PUBLIC_CAIRN_WS_URL) || "";
      let wsBase: string;
      if (wsEnv) {
        wsBase = wsEnv;
      } else {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsBase = `${proto}//${window.location.host}`;
      }
      const wsUrl = `${wsBase}/api/terminal/ws/${host.id}`;

      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        setStatus("connected");
        // Send initial terminal size
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          ws!.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      };

      ws.onmessage = (event) => {
        if (disposed) return;
        terminal.write(event.data);
      };

      ws.onclose = () => {
        if (disposed) return;
        setStatus("disconnected");
        terminal.write("\r\n\x1b[90m--- Disconnected ---\x1b[0m\r\n");
      };

      ws.onerror = () => {
        if (disposed) return;
        setStatus("disconnected");
        terminal.write("\r\n\x1b[31mConnection error\x1b[0m\r\n");
      };

      // Terminal input → WebSocket
      terminal.onData((data: string) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });

      // Resize handling
      const onResize = () => {
        fitAddon.fit();
        const dims = fitAddon.proposeDimensions();
        if (dims && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      };
      const resizeObserver = new ResizeObserver(onResize);
      if (containerRef.current) {
        resizeObserver.observe(containerRef.current);
      }

      return () => {
        resizeObserver.disconnect();
      };
    }

    const cleanupPromise = init();

    return () => {
      disposed = true;
      cleanupPromise?.then((cleanup) => cleanup?.());
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (termRef.current) {
        termRef.current.dispose();
        termRef.current = null;
      }
    };
  }, [host.id, host.hostname]);

  return (
    <div className="flex flex-col h-full">
      <TerminalStatusBar host={host} status={status} />
      <div ref={containerRef} className="flex-1 min-h-0 bg-[#0a0a0a] p-1" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ttyd terminal (iframe)
// ---------------------------------------------------------------------------
function TtydTerminal({ host }: { host: TerminalHost }) {
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  return (
    <div className="flex flex-col h-full">
      <TerminalStatusBar host={host} status={status} />
      <iframe
        ref={iframeRef}
        src={host.ttyd_url || ""}
        className="flex-1 min-h-0 border-0 w-full bg-[#0a0a0a]"
        onLoad={() => setStatus("connected")}
        onError={() => setStatus("disconnected")}
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status bar (shared by both terminal types)
// ---------------------------------------------------------------------------
function TerminalStatusBar({
  host,
  status,
}: {
  host: TerminalHost;
  status: "connecting" | "connected" | "disconnected";
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-card text-xs">
      {status === "connecting" && (
        <><Loader2 className="h-3 w-3 animate-spin text-yellow-500" /><span className="text-yellow-500">Connecting...</span></>
      )}
      {status === "connected" && (
        <><Wifi className="h-3 w-3 text-green-500" /><span className="text-green-500">Connected</span></>
      )}
      {status === "disconnected" && (
        <><WifiOff className="h-3 w-3 text-red-500" /><span className="text-red-500">Disconnected</span></>
      )}
      <span className="text-muted-foreground ml-auto">{host.name}</span>
      <span className="text-muted-foreground/60">{host.hostname}:{host.port}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// No host selected state
// ---------------------------------------------------------------------------
function NoHostSelected() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-3">
      <TerminalIcon className="h-10 w-10 text-muted-foreground/30" />
      <p className="text-sm text-muted-foreground">Select a host to connect</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function TerminalPage() {
  const [config, setConfig] = useState<TerminalConfig | null>(null);
  const [hosts, setHosts] = useState<TerminalHost[]>([]);
  const [activeHost, setActiveHost] = useState<TerminalHost | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingHost, setEditingHost] = useState<TerminalHost | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await api.terminalConfig();
      setConfig(cfg);
      return cfg;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load terminal config");
      return null;
    }
  }, []);

  const loadHosts = useCallback(async () => {
    try {
      const result = await api.terminalHosts();
      setHosts(result.items);
    } catch {
      // 503 = disabled, which is expected
    }
  }, []);

  useEffect(() => {
    async function init() {
      const cfg = await loadConfig();
      if (cfg && cfg.backend !== "disabled") {
        await loadHosts();
      }
      setLoading(false);
    }
    init();
  }, [loadConfig, loadHosts]);

  const handleDelete = async (id: number) => {
    try {
      await api.terminalDeleteHost(id);
      setHosts((prev) => prev.filter((h) => h.id !== id));
      if (activeHost?.id === id) setActiveHost(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete host");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-8rem)]">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="p-4 md:p-6">
        <ErrorState message={error} />
      </div>
    );
  }

  if (!config || config.backend === "disabled") {
    return <DisabledState />;
  }

  return (
    <div
      className="flex -m-4 md:-m-6"
      style={{ height: "calc(100vh - var(--removed, 0px))" }}
    >
      <HostSidebar
        hosts={hosts}
        activeId={activeHost?.id ?? null}
        onSelect={setActiveHost}
        onAdd={() => { setEditingHost(null); setDialogOpen(true); }}
        onEdit={(host) => { setEditingHost(host); setDialogOpen(true); }}
        onDelete={handleDelete}
        backend={config.backend}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        {activeHost ? (
          config.backend === "native" ? (
            <NativeTerminal key={activeHost.id} host={activeHost} />
          ) : (
            <TtydTerminal key={activeHost.id} host={activeHost} />
          )
        ) : (
          <NoHostSelected />
        )}
      </div>

      <HostDialog
        open={dialogOpen}
        onClose={() => { setDialogOpen(false); setEditingHost(null); }}
        onSaved={loadHosts}
        backend={config.backend}
        editHost={editingHost}
      />
    </div>
  );
}
