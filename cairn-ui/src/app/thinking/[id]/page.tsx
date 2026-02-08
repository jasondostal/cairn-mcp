"use client";

import { useParams } from "next/navigation";
import { api, type ThinkingDetail } from "@/lib/api";
import { formatDate, formatTimeFull } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import {
  Brain,
  Eye,
  HelpCircle,
  Lightbulb,
  GitBranch,
  MessageSquare,
  Target,
} from "lucide-react";

const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  observation: Eye,
  hypothesis: Lightbulb,
  question: HelpCircle,
  reasoning: Brain,
  conclusion: Target,
  alternative: GitBranch,
  branch: GitBranch,
};

function ThoughtCard({
  thought,
}: {
  thought: ThinkingDetail["thoughts"][number];
}) {
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

export default function ThinkingDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const { data: detail, loading, error } = useFetch<ThinkingDetail>(
    () => api.thinkingDetail(id),
    [id]
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message="Failed to load thinking sequence" detail={error} />;
  }

  if (!detail) {
    return <p className="text-sm text-muted-foreground">Sequence not found.</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <div className="flex items-center gap-3">
          <Brain className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-2xl font-semibold">{detail.goal}</h1>
        </div>
        <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Badge
            variant={detail.status === "completed" ? "secondary" : "default"}
          >
            {detail.status}
          </Badge>
          <span>{detail.project}</span>
          <span>·</span>
          <span>{detail.thoughts.length} thoughts</span>
          <span>·</span>
          <span>{formatDate(detail.created_at)}</span>
        </div>
      </div>

      <div>
        {detail.thoughts.map((t) => (
          <ThoughtCard key={t.id} thought={t} />
        ))}
      </div>
    </div>
  );
}
