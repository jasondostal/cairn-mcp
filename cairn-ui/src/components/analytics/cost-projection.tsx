"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { ModelPerformance } from "@/lib/api";

interface CostProjectionProps {
  models: ModelPerformance[];
  days: number;
  costRates?: {
    embedding_per_1k: number;
    llm_input_per_1k: number;
    llm_output_per_1k: number;
  };
}

function formatCost(v: number): string {
  if (v < 0.01) return "<$0.01";
  return `$${v.toFixed(2)}`;
}

export function CostProjection({ models, days, costRates }: CostProjectionProps) {
  const rates = costRates ?? {
    embedding_per_1k: 0.0001,
    llm_input_per_1k: 0.003,
    llm_output_per_1k: 0.015,
  };

  // Calculate costs per model
  let totalCost = 0;
  const modelCosts = models.map((m) => {
    const isEmbedding = m.model.includes("embed") || m.model.includes("titan");
    const inputRate = isEmbedding ? rates.embedding_per_1k : rates.llm_input_per_1k;
    const outputRate = isEmbedding ? rates.embedding_per_1k : rates.llm_output_per_1k;

    const inputCost = (m.tokens_in / 1000) * inputRate;
    const outputCost = (m.tokens_out / 1000) * outputRate;
    const cost = inputCost + outputCost;
    totalCost += cost;
    return { model: m.model, cost };
  });

  // Project monthly/annual
  const dailyRate = days > 0 ? totalCost / days : 0;
  const monthlyCost = dailyRate * 30;
  const annualCost = dailyRate * 365;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium">Cost Projection</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p className="text-xs text-muted-foreground">Period ({days}d)</p>
            <p className="text-lg font-semibold tabular-nums">{formatCost(totalCost)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Monthly (est.)</p>
            <p className="text-lg font-semibold tabular-nums">{formatCost(monthlyCost)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Annual (est.)</p>
            <p className="text-lg font-semibold tabular-nums">{formatCost(annualCost)}</p>
          </div>
        </div>
        {modelCosts.length > 0 && (
          <div className="space-y-1.5 pt-1">
            <p className="text-xs text-muted-foreground">By model</p>
            {modelCosts
              .filter((m) => m.cost > 0)
              .sort((a, b) => b.cost - a.cost)
              .map((m) => (
                <div key={m.model} className="flex items-center justify-between text-xs">
                  <span className="font-mono truncate max-w-[200px]">{m.model}</span>
                  <span className="tabular-nums">{formatCost(m.cost)}</span>
                </div>
              ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
