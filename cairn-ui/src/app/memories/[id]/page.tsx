"use client";

import { useParams, useRouter } from "next/navigation";
import { api, type Memory } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { Tag, FileText, Star, Clock, Network, ArrowLeft } from "lucide-react";

export default function MemoryDetail() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const { data: memory, loading, error } = useFetch<Memory>(
    () => api.memory(id),
    [id]
  );

  if (loading) {
    return (
      <div className="space-y-4 max-w-3xl">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4 max-w-3xl">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="mr-1 h-4 w-4" /> Back
        </Button>
        <ErrorState message="Failed to load memory" detail={error} />
      </div>
    );
  }

  if (!memory) {
    return <p className="text-sm text-muted-foreground">Memory not found.</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="mr-1 h-4 w-4" /> Back
        </Button>
        <h1 className="text-2xl font-semibold">Memory #{memory.id}</h1>
        <Badge variant="outline" className="font-mono">
          {memory.memory_type}
        </Badge>
        {!memory.is_active && <Badge variant="destructive">inactive</Badge>}
      </div>

      {memory.summary && (
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <p className="text-sm">{memory.summary}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Content
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="whitespace-pre-wrap text-sm leading-relaxed font-mono">
            {memory.content}
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Star className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Importance</p>
              <p className="font-mono font-semibold">
                {memory.importance.toFixed(2)}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Created</p>
              <p className="text-sm font-medium">
                {formatDate(memory.created_at)}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="h-4 w-4 text-center text-xs font-bold text-muted-foreground">
              P
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Project</p>
              <p className="text-sm font-medium">{memory.project}</p>
            </div>
          </CardContent>
        </Card>
        {memory.cluster && (
          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <Network className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-xs text-muted-foreground">Cluster</p>
                <p className="text-sm font-medium">{memory.cluster.label}</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {memory.tags.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <Tag className="h-4 w-4" />
            Tags
          </div>
          <div className="flex flex-wrap gap-1.5">
            {memory.tags.map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {memory.auto_tags.length > 0 && (
        <div>
          <div className="mb-2 text-sm text-muted-foreground">Auto Tags</div>
          <div className="flex flex-wrap gap-1.5">
            {memory.auto_tags.map((t) => (
              <Badge key={t} variant="outline">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {memory.related_files.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <FileText className="h-4 w-4" />
            Related Files
          </div>
          <div className="space-y-1">
            {memory.related_files.map((f) => (
              <p key={f} className="font-mono text-sm">
                {f}
              </p>
            ))}
          </div>
        </div>
      )}

      {memory.session_name && (
        <p className="text-xs text-muted-foreground">
          Session: {memory.session_name}
        </p>
      )}

      {memory.inactive_reason && (
        <Card className="border-destructive/50">
          <CardContent className="p-4">
            <p className="text-sm text-destructive">
              Inactive: {memory.inactive_reason}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
