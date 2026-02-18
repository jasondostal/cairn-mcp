"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, type ThinkingDetail } from "@/lib/api";
import { formatDate, formatTimeFull } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import {
  Brain,
  Eye,
  HelpCircle,
  Lightbulb,
  GitBranch,
  MessageSquare,
  Target,
  ChevronDown,
  ChevronRight,
  TreeDeciduous,
  List,
  ArrowLeft,
} from "lucide-react";

type Thought = ThinkingDetail["thoughts"][number];

const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  observation: Eye,
  hypothesis: Lightbulb,
  question: HelpCircle,
  reasoning: Brain,
  conclusion: Target,
  alternative: GitBranch,
  branch: GitBranch,
};

const typeColors: Record<string, string> = {
  observation: "border-l-blue-500/50",
  hypothesis: "border-l-amber-500/50",
  question: "border-l-purple-500/50",
  reasoning: "border-l-cyan-500/50",
  conclusion: "border-l-green-500/50",
  alternative: "border-l-orange-500/50",
  branch: "border-l-orange-500/50",
  assumption: "border-l-rose-500/50",
  analysis: "border-l-indigo-500/50",
  general: "border-l-border",
};

// ── Tree data structure ────────────────────────────────────

interface TreeNode {
  thought: Thought;
  children: TreeNode[];
  depth: number;
}

function buildTree(thoughts: Thought[]): TreeNode[] {
  // Group thoughts: main trunk (no branch) + named branches
  const trunk: Thought[] = [];
  const branches = new Map<string, Thought[]>();

  for (const t of thoughts) {
    if (!t.branch) {
      trunk.push(t);
    } else {
      const list = branches.get(t.branch) ?? [];
      list.push(t);
      branches.set(t.branch, list);
    }
  }

  // Build trunk nodes, inserting branch subtrees at the first
  // 'alternative' or 'branch' typed thought
  const nodes: TreeNode[] = [];
  const insertedBranches = new Set<string>();

  for (const t of trunk) {
    const node: TreeNode = { thought: t, children: [], depth: 0 };
    nodes.push(node);
  }

  // Find where each branch diverges and attach children
  for (const t of thoughts) {
    if (t.branch && (t.type === "alternative" || t.type === "branch") && !insertedBranches.has(t.branch)) {
      insertedBranches.add(t.branch);
      const branchThoughts = branches.get(t.branch) ?? [];
      const branchNodes: TreeNode[] = branchThoughts.map((bt) => ({
        thought: bt,
        children: [],
        depth: 1,
      }));

      // Attach to the last trunk node before this branch thought
      const branchIdx = thoughts.indexOf(t);
      let attachTo: TreeNode | null = null;
      for (let i = nodes.length - 1; i >= 0; i--) {
        const trunkIdx = thoughts.indexOf(nodes[i].thought);
        if (trunkIdx < branchIdx) {
          attachTo = nodes[i];
          break;
        }
      }
      if (attachTo) {
        attachTo.children.push(...branchNodes);
      } else if (nodes.length > 0) {
        nodes[nodes.length - 1].children.push(...branchNodes);
      }
    }
  }

  // Handle branches that don't have an alt/branch typed thought
  for (const [name, branchThoughts] of branches) {
    if (!insertedBranches.has(name)) {
      const branchNodes: TreeNode[] = branchThoughts.map((bt) => ({
        thought: bt,
        children: [],
        depth: 1,
      }));
      if (nodes.length > 0) {
        nodes[nodes.length - 1].children.push(...branchNodes);
      } else {
        nodes.push(...branchNodes);
      }
    }
  }

  return nodes;
}

// ── Tree view components ───────────────────────────────────

function TreeThoughtNode({ node, isLast }: { node: TreeNode; isLast: boolean }) {
  const [collapsed, setCollapsed] = useState(false);
  const Icon = typeIcons[node.thought.type] || MessageSquare;
  const colorClass = typeColors[node.thought.type] || typeColors.general;
  const hasBranches = node.children.length > 0;

  return (
    <div className="relative">
      {/* Connector line from parent */}
      {node.depth > 0 && (
        <div className="absolute -left-4 top-0 bottom-0 w-px bg-border" />
      )}

      <div className={`border-l-2 ${colorClass} pl-3 mb-2`}>
        <div className="flex items-start gap-2">
          {/* Branch toggle */}
          {hasBranches ? (
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="mt-0.5 p-0.5 rounded hover:bg-accent/50 transition-colors shrink-0"
            >
              {collapsed ? (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </button>
          ) : (
            <div className="mt-1 shrink-0">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap mb-1">
              <Badge variant="outline" className="text-xs">
                {node.thought.type}
              </Badge>
              {node.thought.branch && (
                <Badge variant="secondary" className="text-xs">
                  {node.thought.branch}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {formatTimeFull(node.thought.created_at)}
              </span>
              {hasBranches && (
                <span className="text-xs text-muted-foreground">
                  ({node.children.length} branch{node.children.length !== 1 ? "es" : ""})
                </span>
              )}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {node.thought.content}
            </p>
          </div>
        </div>
      </div>

      {/* Branch children */}
      {!collapsed && node.children.length > 0 && (
        <div className="ml-6 pl-4 border-l border-dashed border-border/50">
          {node.children.map((child, i) => (
            <TreeThoughtNode
              key={child.thought.id}
              node={child}
              isLast={i === node.children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ThinkingTree({ thoughts }: { thoughts: Thought[] }) {
  const tree = useMemo(() => buildTree(thoughts), [thoughts]);

  // Count unique branches
  const branches = new Set(thoughts.filter((t) => t.branch).map((t) => t.branch));

  return (
    <div>
      {branches.size > 0 && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">Branches:</span>
          {Array.from(branches).map((b) => (
            <Badge key={b} variant="secondary" className="text-xs">
              <GitBranch className="h-3 w-3 mr-1" />
              {b}
            </Badge>
          ))}
        </div>
      )}
      <div>
        {tree.map((node, i) => (
          <TreeThoughtNode key={node.thought.id} node={node} isLast={i === tree.length - 1} />
        ))}
      </div>
    </div>
  );
}

// ── Linear view (original) ─────────────────────────────────

function ThoughtCard({ thought }: { thought: Thought }) {
  const Icon = typeIcons[thought.type] || MessageSquare;

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="rounded-full bg-muted p-1.5">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
        <div className="flex-1 w-px bg-border" />
      </div>
      <Card className="flex-1 mb-3">
        <CardContent className="p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {thought.type}
            </Badge>
            {thought.branch && (
              <Badge variant="secondary" className="text-xs">
                {thought.branch}
              </Badge>
            )}
            <span className="text-xs text-muted-foreground">
              {formatTimeFull(thought.created_at)}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {thought.content}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────

export default function ThinkingDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [viewMode, setViewMode] = useState<"tree" | "linear">("tree");
  const { data: detail, loading, error } = useFetch<ThinkingDetail>(
    () => api.thinkingDetail(id),
    [id]
  );

  const hasBranches = detail?.thoughts.some((t) => t.branch) ?? false;

  return (
    <PageLayout
      title={detail?.goal ?? "Thinking"}
      titleExtra={<>
        {hasBranches && (
          <div className="flex gap-1">
            <Button
              variant={viewMode === "tree" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("tree")}
            >
              <TreeDeciduous className="h-3.5 w-3.5 mr-1" />
              Tree
            </Button>
            <Button
              variant={viewMode === "linear" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("linear")}
            >
              <List className="h-3.5 w-3.5 mr-1" />
              Linear
            </Button>
          </div>
        )}
        <Link href="/thinking">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
      </>}
    >
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-40" />
        </div>
      )}

      {!loading && error && <ErrorState message="Failed to load thinking sequence" detail={error} />}

      {!loading && !error && !detail && <EmptyState message="Sequence not found." />}

      {!loading && !error && detail && (
        <div className="space-y-6 max-w-3xl">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge
              variant={detail.status === "completed" ? "secondary" : "default"}
            >
              {detail.status}
            </Badge>
            <Link href={`/projects/${encodeURIComponent(detail.project)}`} className="text-primary hover:underline">{detail.project}</Link>
            <span>&middot;</span>
            <span>{detail.thoughts.length} thoughts</span>
            <span>&middot;</span>
            <span>{formatDate(detail.created_at)}</span>
          </div>

          {viewMode === "tree" ? (
            <ThinkingTree thoughts={detail.thoughts} />
          ) : (
            <div>
              {detail.thoughts.map((t) => (
                <ThoughtCard key={t.id} thought={t} />
              ))}
            </div>
          )}
        </div>
      )}
    </PageLayout>
  );
}
