"use client";

import { useEffect, useState } from "react";
import { api, type Rule } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { ImportanceBadge } from "@/components/importance-badge";
import { RuleSheet } from "@/components/rule-sheet";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { Shield } from "lucide-react";

function RuleCard({ rule, onClick }: { rule: Rule; onClick: () => void }) {
  return (
    <Card className="transition-colors hover:border-primary/30 cursor-pointer" onClick={onClick}>
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

function RuleDenseRow({ rule, onClick }: { rule: Rule; onClick: () => void }) {
  const truncated = rule.content.length > 120 ? rule.content.slice(0, 120) + "…" : rule.content;
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
      onClick={onClick}
    >
      <Shield className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <Badge variant="outline" className="text-xs shrink-0">{rule.project}</Badge>
      <span className="flex-1 truncate">{truncated}</span>
      <span className="shrink-0"><ImportanceBadge importance={rule.importance} /></span>
      <span className="text-xs text-muted-foreground shrink-0">{formatDate(rule.created_at)}</span>
    </div>
  );
}

function RulesList({ rules, dense, onSelect }: { rules: Rule[]; dense: boolean; onSelect: (rule: Rule) => void }) {
  if (dense) {
    return (
      <div className="rounded-md border border-border divide-y divide-border">
        {rules.map((r) => (
          <RuleDenseRow key={r.id} rule={r} onClick={() => onSelect(r)} />
        ))}
      </div>
    );
  }
  return (
    <PaginatedList
      items={rules}
      noun="rules"
      keyExtractor={(r) => r.id}
      renderItem={(r) => <RuleCard rule={r} onClick={() => onSelect(r)} />}
    />
  );
}

export default function RulesPage() {
  const filters = usePageFilters({ defaultDense: false });
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<Rule | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .rules(filters.showAllProjects ? undefined : { project: filters.projectFilter.join(",") })
      .then((r) => setRules(r.items))
      .catch((err) => setError(err?.message || "Failed to load rules"))
      .finally(() => setLoading(false));
  }, [filters.projectFilter, filters.showAllProjects]);

  function openRuleSheet(rule: Rule) {
    setSelectedRule(rule);
    setSheetOpen(true);
  }

  return (
    <PageLayout
      title="Rules"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={<PageFilters filters={filters} />}
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={4} />}

      {error && <ErrorState message="Failed to load rules" detail={error} />}

      {!loading && !filters.projectsLoading && !error && rules.length === 0 && (
        <EmptyState message="No rules found." detail="Rules are memories with type 'rule' — they guide agent behavior at session start." />
      )}

      {!loading && !filters.projectsLoading && !error && rules.length > 0 && (
        <RulesList rules={rules} dense={filters.dense} onSelect={openRuleSheet} />
      )}

      <RuleSheet
        rule={selectedRule}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
