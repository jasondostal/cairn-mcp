"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type Task } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { CheckCircle, Circle, Link2, ArrowUpRight } from "lucide-react";

interface TaskSheetProps {
  task: Task | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted?: () => void;
}

export function TaskSheet({ task, open, onOpenChange, onCompleted }: TaskSheetProps) {
  const done = task?.status === "completed";
  const [completing, setCompleting] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const router = useRouter();

  const handleComplete = async () => {
    if (!task) return;
    setCompleting(true);
    try {
      await api.taskComplete(task.id);
      onCompleted?.();
      onOpenChange(false);
    } catch {
      // silent — user sees the sheet stays open
    } finally {
      setCompleting(false);
    }
  };

  const handlePromote = async () => {
    if (!task) return;
    setPromoting(true);
    try {
      const result = await api.taskPromote(task.id);
      onCompleted?.();
      onOpenChange(false);
      router.push(`/work-items?id=${result.work_item.id}`);
    } catch {
      // silent
    } finally {
      setPromoting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto">
        {task && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2">
                {done ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground" />
                )}
                <Badge
                  variant={done ? "secondary" : "default"}
                  className="text-xs"
                >
                  {task.status}
                </Badge>
                {task.project && (
                  <Badge variant="outline" className="text-xs">
                    {task.project}
                  </Badge>
                )}
              </div>
              <SheetTitle className="text-base">
                Task #{task.id}
              </SheetTitle>
              <SheetDescription>
                {formatDateTime(task.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              <Separator />

              <div>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Description
                </h3>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {task.description}
                </p>
              </div>

              {task.linked_memories.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Link2 className="h-3 w-3" /> Linked Memories ({task.linked_memories.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {task.linked_memories.map((id) => (
                        <Link
                          key={id}
                          href={`/memories/${id}`}
                          onClick={() => onOpenChange(false)}
                          className="text-sm text-primary hover:underline font-mono"
                        >
                          #{id}
                        </Link>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {!done && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <Button
                      onClick={handleComplete}
                      disabled={completing || promoting}
                      className="w-full"
                      size="sm"
                    >
                      <CheckCircle className="mr-2 h-4 w-4" />
                      {completing ? "Completing..." : "Mark Complete"}
                    </Button>
                    <Button
                      onClick={handlePromote}
                      disabled={promoting || completing}
                      variant="outline"
                      className="w-full"
                      size="sm"
                    >
                      <ArrowUpRight className="mr-2 h-4 w-4" />
                      {promoting ? "Promoting..." : "Promote to Work Item"}
                    </Button>
                  </div>
                </>
              )}

              <Separator />
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>ID: {task.id}</p>
                <p>Created: {formatDateTime(task.created_at)}</p>
                {task.completed_at && (
                  <p>Completed: {formatDateTime(task.completed_at)}</p>
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
