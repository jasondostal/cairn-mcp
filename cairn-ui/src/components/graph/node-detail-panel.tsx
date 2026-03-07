"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type KGStatement } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";
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
import {
  type SimNode,
  type SimLink,
  ENTITY_TYPES,
  ENTITY_COLORS,
  DEFAULT_NODE_COLOR,
} from "./graph-types";

// ────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────

interface NodeDetailPanelProps {
  selectedNode: SimNode;
  linksRef: React.RefObject<SimLink[]>;
  connectionCount: (nodeId: string) => number;
  onSelectNode: (node: SimNode | null) => void;
  onReload: () => void;
}

// ────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────

export function NodeDetailPanel({
  selectedNode,
  linksRef,
  connectionCount,
  onSelectNode,
  onReload,
}: NodeDetailPanelProps) {
  // --- Compute connections from links ref ---
  const connections = useMemo(() => {
    if (selectedNode.meta.kind !== "neo4j") return [];
    return linksRef.current
      .filter((l) => {
        const s = l.source as SimNode;
        const tgt = l.target as SimNode;
        return s.nodeId === selectedNode.nodeId || tgt.nodeId === selectedNode.nodeId;
      })
      .map((l) => {
        const s = l.source as SimNode;
        const tgt = l.target as SimNode;
        const other = s.nodeId === selectedNode.nodeId ? tgt : s;
        const direction = s.nodeId === selectedNode.nodeId ? "out" : "in";
        const em = l.edgeMeta.kind === "neo4j" ? l.edgeMeta : null;
        return {
          other,
          predicate: l.edgeLabel,
          fact: em?.fact ?? "",
          aspect: em?.aspect ?? "",
          direction,
        };
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode.nodeId]);

  // --- Entity editing ---
  const [editingEntity, setEditingEntity] = useState(false);
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [deleteConfirmEntity, setDeleteConfirmEntity] = useState<SimNode | null>(null);
  const [entityStatements, setEntityStatements] = useState<KGStatement[]>([]);
  const [statementsLoading, setStatementsLoading] = useState(false);

  // Load statements when selected entity changes
  useEffect(() => {
    if (selectedNode.meta.kind === "neo4j") {
      loadEntityStatements(selectedNode.nodeId);
    }
    setEditingEntity(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode.nodeId]);

  async function loadEntityStatements(entityUuid: string) {
    setStatementsLoading(true);
    try {
      const result = await api.entityStatements(entityUuid);
      setEntityStatements(result.statements);
    } catch {
      setEntityStatements([]);
    } finally {
      setStatementsLoading(false);
    }
  }

  function startEditEntity() {
    if (selectedNode.meta.kind !== "neo4j") return;
    setEditName(selectedNode.label);
    setEditType(selectedNode.meta.entity_type);
    setEditingEntity(true);
  }

  async function saveEditEntity() {
    if (selectedNode.meta.kind !== "neo4j") return;
    setEditSaving(true);
    try {
      await api.updateEntity(selectedNode.nodeId, {
        name: editName.trim() || undefined,
        entity_type: editType || undefined,
      });
      setEditingEntity(false);
      onSelectNode(null);
      onReload();
    } catch {
      // silent
    } finally {
      setEditSaving(false);
    }
  }

  async function confirmDeleteEntity() {
    if (!deleteConfirmEntity || deleteConfirmEntity.meta.kind !== "neo4j") return;
    try {
      await api.deleteEntity(deleteConfirmEntity.nodeId);
      setDeleteConfirmEntity(null);
      onSelectNode(null);
      onReload();
    } catch {
      // silent
    }
  }

  async function handleInvalidateStatement(stmtUuid: string) {
    try {
      await api.invalidateStatement(stmtUuid);
      loadEntityStatements(selectedNode.nodeId);
    } catch {
      // silent
    }
  }

  if (selectedNode.meta.kind !== "neo4j") return null;

  return (
    <>
      <div className="w-80 shrink-0 space-y-3 rounded-lg border border-border bg-card p-4 overflow-y-auto max-h-[640px]">
        {/* Header — view or edit mode */}
        {editingEntity ? (
          <div className="space-y-2">
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="text-sm font-semibold"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && saveEditEntity()}
            />
            <SingleSelect
              options={ENTITY_TYPES.filter((t) => t !== "all").map((t) => ({ value: t, label: t }))}
              value={editType}
              onValueChange={setEditType}
              className="w-full"
            />
            <div className="flex gap-1">
              <Button size="sm" onClick={saveEditEntity} disabled={editSaving} className="flex-1">
                {editSaving ? "Saving..." : "Save"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditingEntity(false)} className="flex-1">
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-2">
              <div
                className="h-3 w-3 rounded-full shrink-0"
                style={{
                  backgroundColor:
                    ENTITY_COLORS[selectedNode.meta.entity_type] ||
                    DEFAULT_NODE_COLOR,
                }}
              />
              <h3 className="font-semibold text-sm">{selectedNode.label}</h3>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {selectedNode.meta.entity_type} &middot;{" "}
              {selectedNode.meta.stmt_count} statements &middot;{" "}
              {connectionCount(selectedNode.nodeId)} connections
            </p>
            {/* Action buttons */}
            <div className="flex gap-1 mt-2">
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={startEditEntity}>
                Edit
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                onClick={() => setDeleteConfirmEntity(selectedNode)}
              >
                Delete
              </Button>
            </div>
          </div>
        )}

        {/* Relationships */}
        {connections.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-muted-foreground mb-2">
              Relationships ({connections.length})
            </h4>
            <div className="space-y-2 max-h-[200px] overflow-y-auto">
              {connections.map((conn, i) => (
                <div
                  key={i}
                  className="rounded border border-border/50 p-2 text-xs cursor-pointer hover:bg-accent/50"
                  onClick={() => onSelectNode(conn.other)}
                >
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">
                      {conn.direction === "out" ? "\u2192" : "\u2190"}
                    </span>
                    <span className="font-medium">{conn.predicate}</span>
                    <span className="text-muted-foreground">
                      {conn.direction === "out" ? "\u2192" : "\u2190"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div
                      className="h-2 w-2 rounded-full shrink-0"
                      style={{
                        backgroundColor:
                          conn.other.meta.kind === "neo4j"
                            ? ENTITY_COLORS[conn.other.meta.entity_type] ||
                              DEFAULT_NODE_COLOR
                            : DEFAULT_NODE_COLOR,
                      }}
                    />
                    <span>{conn.other.label}</span>
                  </div>
                  <p className="text-muted-foreground/70 mt-0.5 line-clamp-2">
                    {conn.fact}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Statements */}
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">
            Statements {statementsLoading ? "" : `(${entityStatements.length})`}
          </h4>
          {statementsLoading ? (
            <p className="text-xs text-muted-foreground">Loading...</p>
          ) : entityStatements.length === 0 ? (
            <p className="text-xs text-muted-foreground">No statements</p>
          ) : (
            <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
              {entityStatements.map((stmt) => (
                <div
                  key={stmt.uuid}
                  className="group rounded border border-border/50 p-2 text-xs"
                >
                  <p className="text-foreground/90">{stmt.fact}</p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-muted-foreground">{stmt.aspect}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 px-1 text-[10px] opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive"
                      onClick={() => handleInvalidateStatement(stmt.uuid)}
                    >
                      Invalidate
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="w-full"
          onClick={() => onSelectNode(null)}
        >
          Close
        </Button>
      </div>

      {/* Delete entity confirmation */}
      <AlertDialog open={!!deleteConfirmEntity} onOpenChange={(open) => !open && setDeleteConfirmEntity(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete entity?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleteConfirmEntity?.label}&rdquo; and its orphaned statements will be permanently deleted.
              {deleteConfirmEntity && (
                <span className="block mt-1">
                  {deleteConfirmEntity.meta.kind === "neo4j" && (
                    <>{deleteConfirmEntity.meta.stmt_count} statements, {connectionCount(deleteConfirmEntity.nodeId)} connections</>
                  )}
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDeleteEntity}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
