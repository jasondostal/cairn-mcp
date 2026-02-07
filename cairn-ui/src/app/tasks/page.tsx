"use client";

import { useEffect, useState } from "react";
import { api, type Task, type Project } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { CheckCircle, Circle, Link2 } from "lucide-react";

function TaskCard({ task }: { task: Task }) {
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
            <Badge
              variant={done ? "secondary" : "default"}
              className="text-xs"
            >
              {task.status}
            </Badge>
            <span>
              {new Date(task.created_at).toLocaleDateString()}
            </span>
            {task.completed_at && (
              <span>
                completed{" "}
                {new Date(task.completed_at).toLocaleDateString()}
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

export default function TasksPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCompleted, setShowCompleted] = useState(false);

  useEffect(() => {
    api
      .projects()
      .then((p) => {
        setProjects(p);
        if (p.length > 0) setSelected(p[0].name);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    api
      .tasks(selected, {
        include_completed: showCompleted ? "true" : undefined,
      })
      .then(setTasks)
      .finally(() => setLoading(false));
  }, [selected, showCompleted]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Tasks</h1>

      <div className="flex items-center gap-2">
        <div className="flex gap-1 flex-wrap">
          {projects.map((p) => (
            <Button
              key={p.id}
              variant={selected === p.name ? "default" : "outline"}
              size="sm"
              onClick={() => setSelected(p.name)}
            >
              {p.name}
            </Button>
          ))}
        </div>
        <Button
          variant={showCompleted ? "default" : "outline"}
          size="sm"
          onClick={() => setShowCompleted(!showCompleted)}
        >
          {showCompleted ? "Hide" : "Show"} completed
        </Button>
      </div>

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {!loading && tasks.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No tasks for {selected}.
        </p>
      )}

      {!loading && tasks.length > 0 && (
        <div className="space-y-2">
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} />
          ))}
        </div>
      )}
    </div>
  );
}
