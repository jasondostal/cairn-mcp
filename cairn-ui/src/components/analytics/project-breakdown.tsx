"use client";

import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ProjectBreakdown as PB } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

function formatTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function TrendIcon({ trend }: { trend: "up" | "down" | "flat" }) {
  if (trend === "up") return <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />;
  if (trend === "down") return <TrendingDown className="h-3.5 w-3.5 text-destructive" />;
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
}

export function ProjectBreakdown({ items }: { items: PB[] }) {
  if (!items.length) {
    return (
      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">No project data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium">Project Breakdown</h3>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Project</TableHead>
                <TableHead className="text-right">Ops</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">Avg Latency</TableHead>
                <TableHead className="text-right">Error Rate</TableHead>
                <TableHead className="text-center">Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((p) => (
                <TableRow key={p.project}>
                  <TableCell className="font-medium">{p.project}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.operations.toLocaleString()}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatTokens(p.tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.avg_latency.toFixed(0)}ms</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.error_rate > 0 ? (
                      <span className="text-destructive">{p.error_rate.toFixed(1)}%</span>
                    ) : (
                      <span className="text-muted-foreground">0%</span>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    <TrendIcon trend={p.trend} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
