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
import type { ModelPerformance as ModelPerf } from "@/lib/api";

function formatTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

export function ModelPerformance({ items }: { items: ModelPerf[] }) {
  if (!items.length) {
    return (
      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">No model data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium">Model Performance</h3>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">p50</TableHead>
                <TableHead className="text-right">p95</TableHead>
                <TableHead className="text-right">p99</TableHead>
                <TableHead className="text-right">Errors</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((m) => (
                <TableRow key={m.model}>
                  <TableCell className="font-mono text-xs">{m.model}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.calls.toLocaleString()}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatTokens(m.tokens_in + m.tokens_out)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.latency_p50.toFixed(0)}ms</TableCell>
                  <TableCell className="text-right tabular-nums">{m.latency_p95.toFixed(0)}ms</TableCell>
                  <TableCell className="text-right tabular-nums">{m.latency_p99.toFixed(0)}ms</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {m.error_rate > 0 ? (
                      <span className="text-destructive">{m.error_rate.toFixed(1)}%</span>
                    ) : (
                      <span className="text-muted-foreground">0%</span>
                    )}
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
