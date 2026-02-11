"use client";

import { useEffect, useState } from "react";
import { api, type Task } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { MultiSelect } from "@/components/ui/multi-select";
import { TaskSheet } from "@/components/task-sheet";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { CheckCircle, Circle, Link2, LayoutList, LayoutGrid } from "lucide-react";

function TaskCard({ task, showProject, onClick }: { task: Task; showProject?: boolean; onClick: () => void }) {
  const done = task.status === "completed";

  return (
    <Card className={`transition-colors hover:border-primary/30 cursor-pointer ${done ? "opacity-60" : ""}`} onClick={onClick}>
      <CardContent className="flex items-start gap-3 p-4">
        {done ? (
          <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
        ) : (
          <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="flex-1 space-y-1">
          <p className="text-sm">{task.description}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>#{task.id}</span>
            {showProject && task.project && (
              <Badge variant="secondary" className="text-xs">
                {task.project}
              </Badge>
            )}
            <Badge
              variant={done ? "secondary" : "default"}
              className="text-xs"
            >
              {task.status}
            </Badge>
            <span>
              {formatDate(task.created_at)}
            </span>
            {task.completed_at && (
              <span>
                completed{" "}
                {formatDate(task.completed_at)}
              </span>
            )}
          </div>
          {task.linked_memories.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Link2 className="h-3 w-3" />
              {task.linked_memories.length} linked{" "}
              {task.linked_memories.length === 1 ? "memory" : "memories"}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function TaskDenseRow({ task, showProject, onClick }: { task: Task; showProject?: boolean; onClick: () => void }) {
  const done = task.status === "completed";
  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer ${done ? "opacity-50" : ""}`}
      onClick={onClick}
    >
      {done ? (
        <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-500" />
      ) : (
        <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className="font-mono text-xs text-muted-foreground shrink-0">#{task.id}</span>
      <span className="flex-1 truncate">{task.description}</span>
      {showProject && task.project && (
        <Badge variant="secondary" className="text-xs shrink-0">{task.project}</Badge>
      )}
      {task.linked_memories.length > 0 && (
        <span className="text-xs text-muted-foreground shrink-0">
          <Link2 className="inline h-3 w-3" /> {task.linked_memories.length}
        </span>
      )}
      <span className="text-xs text-muted-foreground shrink-0">{formatDate(task.created_at)}</span>
    </div>
  );
}

function TasksList({ tasks, showProject, dense, onSelect }: { tasks: Task[]; showProject?: boolean; dense?: boolean; onSelect: (task: Task) => void }) {
  if (dense) {
    return (
      <div className="rounded-md border border-border divide-y divide-border">
        {tasks.map((t) => (
          <TaskDenseRow key={t.id} task={t} showProject={showProject} onClick={() => onSelect(t)} />
        ))}
      </div>
    );
  }
  return (
    <PaginatedList
      items={tasks}
      noun="tasks"
      keyExtractor={(t) => t.id}
      renderItem={(t) => <TaskCard task={t} showProject={showProject} onClick={() => onSelect(t)} />}
      gap="space-y-2"
    />
  );
}

export default function TasksPage() {
  const { projects, selected, setSelected, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [projectFilter, setProjectFilter] = useState<string[]>([]);
  const [dense, setDense] = useState(true);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const showAll = projectFilter.length === 0;

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .tasks(showAll ? undefined : projectFilter.join(","), {
        include_completed: showCompleted ? "true" : undefined,
      })
      .then((r) => setTasks(r.items))
      .catch((err) => setError(err?.message || "Failed to load tasks"))
      .finally(() => setLoading(false));
  }, [projectFilter, showCompleted, showAll]);

  const projectOptions = projects.map((p) => ({ value: p.name, label: p.name }));

  function openTaskSheet(task: Task) {
    setSelectedTask(task);
    setSheetOpen(true);
  }

  return (
    <PageLayout
      title="Tasks"
      titleExtra={
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={() => setDense(!dense)}
          title={dense ? "Card view" : "Dense view"}
        >
          {dense ? <LayoutGrid className="h-4 w-4" /> : <LayoutList className="h-4 w-4" />}
        </Button>
      }
      filters={
        <div className="flex items-center gap-2 flex-wrap">
          <MultiSelect
            options={projectOptions}
            value={projectFilter}
            onValueChange={setProjectFilter}
            placeholder="All projects"
            searchPlaceholder="Search projects…"
            maxCount={2}
          />
          <Button
            variant={showCompleted ? "default" : "outline"}
            size="sm"
            onClick={() => setShowCompleted(!showCompleted)}
          >
            {showCompleted ? "Hide" : "Show"} completed
          </Button>
        </div>
      }
    >
      {(loading || projectsLoading) && <SkeletonList count={4} height="h-20" />}

      {(error || projectsError) && <ErrorState message="Failed to load tasks" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && tasks.length === 0 && (
        <EmptyState
          message={showAll
            ? "No tasks yet."
            : `No tasks for ${projectFilter.join(", ")}.`}
        />
      )}

      {!loading && !projectsLoading && !error && !projectsError && tasks.length > 0 && (
        <TasksList tasks={tasks} showProject={showAll} dense={dense} onSelect={openTaskSheet} />
      )}

      <TaskSheet
        task={selectedTask}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
