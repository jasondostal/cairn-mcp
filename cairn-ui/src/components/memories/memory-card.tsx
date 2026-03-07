"use client";

import Link from "next/link";
import type { TimelineMemory } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { scoreColor, salienceColor } from "@/lib/colors";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ProjectPill } from "@/components/project-pill";
import { TagList } from "@/components/tag-list";
import { Network, Pin, Zap, Archive, Lightbulb } from "lucide-react";
import { LC } from "./memory-filters";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function isEphemeral(m: TimelineMemory): boolean {
  return m.salience != null;
}

/* ------------------------------------------------------------------ */
/*  Cluster Tag                                                        */
/* ------------------------------------------------------------------ */

function ClusterTag({ cluster }: { cluster: { id: number; label: string; size: number } }) {
  return (
    <Link
      href={`/search?q=${encodeURIComponent(cluster.label)}`}
      className="inline-flex items-center gap-1 rounded-full bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <Network className="size-3" />
      {cluster.label}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Salience Bar (ephemeral items)                                     */
/* ------------------------------------------------------------------ */

function SalienceBar({ salience }: { salience: number }) {
  return (
    <div
      className="w-1 rounded-full self-stretch shrink-0"
      style={{
        backgroundColor: LC.ephemeral,
        opacity: Math.max(0.15, salience),
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Ephemeral Actions (boost / pin / archive)                          */
/* ------------------------------------------------------------------ */

export function EphemeralActions({
  memory,
  onAction,
  size = "default",
}: {
  memory: TimelineMemory;
  onAction: (id: number, action: string) => void;
  size?: "default" | "dense";
}) {
  const btnCls = size === "dense" ? "h-5 w-5 p-0" : "h-6 w-6 p-0";
  const iconCls = size === "dense" ? "h-2.5 w-2.5" : "h-3 w-3";

  return (
    <div className={`flex ${size === "dense" ? "gap-0.5" : "gap-1"}`}>
      <Button variant="ghost" size="sm" className={btnCls} title="Boost salience"
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, "boost"); }}>
        <Zap className={iconCls} />
      </Button>
      <Button variant="ghost" size="sm" className={btnCls} title={memory.pinned ? "Unpin" : "Pin"}
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, memory.pinned ? "unpin" : "pin"); }}>
        <Pin className={iconCls} />
      </Button>
      <Button variant="ghost" size="sm" className={btnCls} title="Archive"
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, "archive"); }}>
        <Archive className={iconCls} />
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Score Bar (importance or salience)                                  */
/* ------------------------------------------------------------------ */

export function ScoreBar({ value, variant }: { value: number; variant: "importance" | "salience" }) {
  const c = variant === "salience" ? salienceColor(value) : scoreColor(value);
  const pct = (value * 100).toFixed(0);
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <div className="w-10 h-1.5 rounded-full bg-muted/40 overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.max(5, value * 100)}%`, backgroundColor: c }}
        />
      </div>
      <span className="font-mono text-[11px] tabular-nums w-7 text-right" style={{ color: c }}>
        {variant === "salience" ? `${pct}%` : value.toFixed(2)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Memory Card                                                        */
/* ------------------------------------------------------------------ */

interface MemoryCardProps {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
  onAction: (id: number, action: string) => void;
  isActive?: boolean;
  cardRef?: React.RefObject<HTMLDivElement | null>;
}

export function MemoryCard({
  memory,
  onSelect,
  onAction,
  isActive,
  cardRef,
}: MemoryCardProps) {
  const content =
    memory.content.length > 200
      ? memory.content.slice(0, 200) + "\u2026"
      : memory.content;
  const eph = isEphemeral(memory);


  return (
    <Card
      ref={isActive ? cardRef : undefined}
      className={`transition-colors hover:border-primary/30 cursor-pointer ${isActive ? "border-primary/50 bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      <div className="flex">
        {eph && <SalienceBar salience={memory.salience!} />}
        <CardContent className={`space-y-2 p-4 flex-1 min-w-0 ${eph ? "pl-3" : ""}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              {eph && <Lightbulb className="h-4 w-4 text-muted-foreground shrink-0" />}
              <MemoryTypeBadge type={memory.memory_type} />
              <ProjectPill name={memory.project} />
              {eph && memory.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
            </div>
            <div className="shrink-0">
              {eph ? (
                <ScoreBar value={memory.salience!} variant="salience" />
              ) : (
                <ScoreBar value={memory.importance} variant="importance" />
              )}
            </div>
          </div>

          {memory.summary && !eph && (
            <p className="text-sm font-medium">{memory.summary}</p>
          )}

          <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
            {content}
          </p>

          {!eph && (
            <div className="flex items-center gap-2 flex-wrap">
              <TagList tags={memory.tags} />
              {memory.cluster && <ClusterTag cluster={memory.cluster} />}
            </div>
          )}

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>#{memory.id}</span>
            {eph && memory.author && (
              <>
                <span>&middot;</span>
                <span>{memory.author}</span>
              </>
            )}
            <span>&middot;</span>
            <span>{formatTime(memory.created_at)}</span>
            {eph && (
              <div className="ml-auto">
                <EphemeralActions memory={memory} onAction={onAction} />
              </div>
            )}
          </div>
        </CardContent>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Memory Dense Row                                                   */
/* ------------------------------------------------------------------ */

interface MemoryDenseRowProps {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
  onAction: (id: number, action: string) => void;
  isActive?: boolean;
  cardRef?: React.RefObject<HTMLDivElement | null>;
}

export function MemoryDenseRow({
  memory,
  onSelect,
  onAction,
  isActive,
  cardRef,
}: MemoryDenseRowProps) {
  const eph = isEphemeral(memory);


  return (
    <div
      ref={isActive ? cardRef : undefined}
      className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer ${isActive ? "bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      {eph && (
        <div
          className="w-1 h-4 rounded-full shrink-0"
          style={{
            backgroundColor: LC.ephemeral,
            opacity: Math.max(0.15, memory.salience!),
          }}
        />
      )}
      <span className="font-mono text-xs text-muted-foreground shrink-0">#{memory.id}</span>
      <MemoryTypeBadge type={memory.memory_type} />
      {eph && memory.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
      <span className="flex-1 truncate">{memory.summary || memory.content}</span>
      <ProjectPill name={memory.project} />
      {eph ? (
        <ScoreBar value={memory.salience!} variant="salience" />
      ) : (
        <ScoreBar value={memory.importance} variant="importance" />
      )}
      <span className="text-xs text-muted-foreground shrink-0">{formatTime(memory.created_at)}</span>
      {eph && <EphemeralActions memory={memory} onAction={onAction} size="dense" />}
    </div>
  );
}
