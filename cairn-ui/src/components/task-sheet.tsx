"use client";

import Link from "next/link";
import type { Task } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { CheckCircle, Circle, Link2 } from "lucide-react";

interface TaskSheetProps {
  task: Task | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TaskSheet({ task, open, onOpenChange }: TaskSheetProps) {
  const done = task?.status === "completed";

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
