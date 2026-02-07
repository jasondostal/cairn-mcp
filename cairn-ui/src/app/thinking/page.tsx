"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ThinkingSequence, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Brain } from "lucide-react";

export default function ThinkingPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState("");
  const [sequences, setSequences] = useState<ThinkingSequence[]>([]);
  const [loading, setLoading] = useState(true);

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
      .thinking(selected)
      .then(setSequences)
      .finally(() => setLoading(false));
  }, [selected]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Thinking</h1>

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

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {!loading && sequences.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No thinking sequences for {selected}.
        </p>
      )}

      {!loading && sequences.length > 0 && (
        <div className="space-y-3">
          {sequences.map((s) => (
            <Link key={s.sequence_id} href={`/thinking/${s.sequence_id}`}>
              <Card className="transition-colors hover:border-primary/30">
                <CardHeader className="p-4 pb-2">
                  <div className="flex items-center gap-2">
                    <Brain className="h-4 w-4 text-muted-foreground" />
                    <CardTitle className="text-sm font-medium">
                      {s.goal}
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge
                      variant={
                        s.status === "completed" ? "secondary" : "default"
                      }
                      className="text-xs"
                    >
                      {s.status}
                    </Badge>
                    <span>
                      {s.thought_count} thought
                      {s.thought_count !== 1 && "s"}
                    </span>
                    <span>·</span>
                    <span>
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
