"use client";

import { useEffect, useState } from "react";
import { api, type Task } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { ProjectSelector } from "@/components/project-selector";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { CheckCircle, Circle, Link2 } from "lucide-react";

function TaskCard({ task, showProject }: { task: Task; showProject?: boolean }) {
  const done = task.status === "completed";

  return (
    <Card className={done ? "opacity-60" : ""}>
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

function TasksList({ tasks, showProject }: { tasks: Task[]; showProject?: boolean }) {
  return (
    <PaginatedList
      items={tasks}
      noun="tasks"
      keyExtractor={(t) => t.id}
      renderItem={(t) => <TaskCard task={t} showProject={showProject} />}
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
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!showAll && !selected) return;
    setLoading(true);
    setError(null);
    api
      .tasks(showAll ? undefined : selected, {
        include_completed: showCompleted ? "true" : undefined,
      })
      .then((r) => setTasks(r.items))
      .catch((err) => setError(err?.message || "Failed to load tasks"))
      .finally(() => setLoading(false));
  }, [selected, showCompleted, showAll]);

  function handleShowAll() {
    setShowAll(true);
  }

  function handleSelectProject(name: string) {
    setShowAll(false);
    setSelected(name);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Tasks</h1>

      <div className="flex items-center gap-2">
        <div className="flex gap-1 flex-wrap">
          <Button
            variant={showAll ? "default" : "outline"}
            size="sm"
            onClick={handleShowAll}
          >
            All
          </Button>
          <ProjectSelector
            projects={projects}
            selected={showAll ? "" : selected}
            onSelect={handleSelectProject}
          />
        </div>
        <Button
          variant={showCompleted ? "default" : "outline"}
          size="sm"
          onClick={() => setShowCompleted(!showCompleted)}
        >
          {showCompleted ? "Hide" : "Show"} completed
        </Button>
      </div>

      {(loading || projectsLoading) && <SkeletonList count={4} height="h-20" />}

      {(error || projectsError) && <ErrorState message="Failed to load tasks" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && tasks.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {showAll
            ? "No tasks yet."
            : `No tasks for ${selected}.`}
        </p>
      )}

      {!loading && !projectsLoading && !error && !projectsError && tasks.length > 0 && (
        <TasksList tasks={tasks} showProject={showAll} />
      )}
    </div>
  );
}
