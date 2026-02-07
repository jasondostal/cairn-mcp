"use client";

import { useEffect, useState } from "react";
import { api, type Rule, type Project } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { usePagination, PaginationControls } from "@/components/pagination";
import { Shield, Star } from "lucide-react";

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
          <div className="flex items-center gap-1 shrink-0">
            <Star className="h-3 w-3 text-muted-foreground" />
            <span className="font-mono text-xs text-muted-foreground">
              {rule.importance.toFixed(2)}
            </span>
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
          #{rule.id} · {new Date(rule.created_at).toLocaleDateString()}
        </p>
      </CardContent>
    </Card>
  );
}

function RulesList({ rules }: { rules: Rule[] }) {
  const { page, totalPages, pageItems, setPage } = usePagination(rules, 20);

  return (
    <div className="space-y-3">
      <PaginationControls
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        total={rules.length}
        noun="rules"
      />
      {pageItems.map((r) => (
        <RuleCard key={r.id} rule={r} />
      ))}
      {totalPages > 1 && (
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          total={rules.length}
          noun="rules"
        />
      )}
    </div>
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
        setProjects(p);
        setRules(r);
      })
      .catch((err) => setError(err?.message || "Failed to load rules"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .rules(selected)
      .then(setRules)
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

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

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
