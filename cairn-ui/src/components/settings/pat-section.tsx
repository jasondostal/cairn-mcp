"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type ApiToken, type ApiTokenCreateResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Key, Plus, Copy, Trash2 } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function PATSection() {
  const { user, authEnabled } = useAuth();
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTokenName, setNewTokenName] = useState("");
  const [newTokenDays, setNewTokenDays] = useState("");
  const [rawToken, setRawToken] = useState<ApiTokenCreateResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState<number | null>(null);

  const loadTokens = useCallback(() => {
    setLoading(true);
    api.authTokens()
      .then(setTokens)
      .catch(() => setTokens([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (authEnabled && user) loadTokens();
  }, [authEnabled, user, loadTokens]);

  if (!authEnabled || !user) return null;

  const handleCreate = async () => {
    if (!newTokenName.trim()) return;
    setCreating(true);
    try {
      const days = newTokenDays ? parseInt(newTokenDays, 10) : undefined;
      const result = await api.authTokenCreate({
        name: newTokenName.trim(),
        expires_in_days: days,
      });
      setRawToken(result);
      setNewTokenName("");
      setNewTokenDays("");
      loadTokens();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create token");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (tokenId: number) => {
    try {
      await api.authTokenRevoke(tokenId);
      toast.success("Token revoked");
      loadTokens();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke token");
    }
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="mb-4">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Key className="h-4 w-4" />
          Personal Access Tokens
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0 space-y-3">
        <p className="text-xs text-muted-foreground">
          Use tokens to authenticate API and MCP clients. Tokens are shown once at creation.
        </p>

        {/* New token revealed */}
        {rawToken && (
          <div className="rounded-md border border-green-500/30 bg-green-500/10 p-3 space-y-2">
            <p className="text-xs font-medium text-green-300">
              Token created — copy it now, it won&apos;t be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded bg-background px-2 py-1 text-xs font-mono break-all select-all">
                {rawToken.raw_token}
              </code>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => handleCopy(rawToken.raw_token)}
              >
                <Copy className="h-3 w-3 mr-1" />
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <Button
              variant="ghost"
              size="xs"
              className="text-xs"
              onClick={() => setRawToken(null)}
            >
              Dismiss
            </Button>
          </div>
        )}

        {/* Create form */}
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label htmlFor="pat-name" className="sr-only">Token name</label>
            <Input
              id="pat-name"
              placeholder="Token name (e.g. claude-code)"
              value={newTokenName}
              onChange={(e) => setNewTokenName(e.target.value)}
              className="h-7 text-xs"
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
          </div>
          <div className="w-28">
            <label htmlFor="pat-days" className="sr-only">Expiration days</label>
            <Input
              id="pat-days"
              type="number"
              placeholder="Days (empty=never)"
              value={newTokenDays}
              onChange={(e) => setNewTokenDays(e.target.value)}
              className="h-7 text-xs"
              min={1}
            />
          </div>
          <Button size="xs" onClick={handleCreate} disabled={creating || !newTokenName.trim()}>
            <Plus className="h-3 w-3 mr-1" />
            Create
          </Button>
        </div>

        {/* Token list */}
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : tokens.length === 0 ? (
          <p className="text-xs text-muted-foreground">No tokens yet.</p>
        ) : (
          <div className="divide-y divide-border">
            {tokens.map((t) => (
              <div key={t.id} className="flex items-center justify-between py-2 text-xs">
                <div className="flex items-center gap-3">
                  <span className="font-medium">{t.name}</span>
                  <code className="text-muted-foreground font-mono">{t.token_prefix}...</code>
                  {t.last_used_at && (
                    <span className="text-muted-foreground">
                      used {new Date(t.last_used_at).toLocaleDateString()}
                    </span>
                  )}
                  {t.expires_at && (
                    <span className={cn(
                      "text-muted-foreground",
                      new Date(t.expires_at) < new Date() && "text-red-400",
                    )}>
                      {new Date(t.expires_at) < new Date()
                        ? "expired"
                        : `expires ${new Date(t.expires_at).toLocaleDateString()}`}
                    </span>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="xs"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => setRevokeConfirm(t.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <AlertDialog open={revokeConfirm !== null} onOpenChange={(open) => !open && setRevokeConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke token?</AlertDialogTitle>
            <AlertDialogDescription>This token will immediately stop working for all clients using it.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => { handleRevoke(revokeConfirm!); setRevokeConfirm(null); }}>
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
