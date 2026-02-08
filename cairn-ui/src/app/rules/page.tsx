"use client";

import { useEffect, useState } from "react";
import { api, type Rule, type Project } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { ImportanceBadge } from "@/components/importance-badge";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { Shield } from "lucide-react";

function RuleCard({ rule }: { rule: Rule }) {
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <Badge variant="outline" className="text-xs">
              {rule.project}
            </Badge>
          </div>
          <div className="shrink-0">
            <ImportanceBadge importance={rule.importance} />
          </div>
        </div>

        <p className="whitespace-pre-wrap text-sm leading-relaxed">
          {rule.content}
        </p>

        {rule.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {rule.tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-xs">
                {t}
              </Badge>
            ))}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          #{rule.id} · {formatDate(rule.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}

function RulesList({ rules }: { rules: Rule[] }) {
  return (
    <PaginatedList
      items={rules}
      noun="rules"
      keyExtractor={(r) => r.id}
      renderItem={(r) => <RuleCard rule={r} />}
    />
  );
}

export default function RulesPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    Promise.all([api.projects(), api.rules()])
      .then(([p, r]) => {
        setProjects(p.items);
        setRules(r.items);
      })
      .catch((err) => setError(err?.message || "Failed to load rules"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .rules(selected ? { project: selected } : undefined)
      .then((r) => setRules(r.items))
      .catch((err) => setError(err?.message || "Failed to load rules"))
      .finally(() => setLoading(false));
  }, [selected]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Rules</h1>

      <div className="flex gap-1 flex-wrap">
        <Button
          variant={selected === undefined ? "default" : "outline"}
          size="sm"
          onClick={() => setSelected(undefined)}
        >
          All
        </Button>
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

      {loading && <SkeletonList count={4} />}

      {error && <ErrorState message="Failed to load rules" detail={error} />}

      {!loading && !error && rules.length === 0 && (
        <p className="text-sm text-muted-foreground">No rules found.</p>
      )}

      {!loading && !error && rules.length > 0 && (
        <RulesList rules={rules} />
      )}
    </div>
  );
}
