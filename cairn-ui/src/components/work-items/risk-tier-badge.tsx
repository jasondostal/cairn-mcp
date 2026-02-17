import { cn } from "@/lib/utils";

const riskConfig: Record<number, { label: string; className: string }> = {
  1: { label: "caution", className: "text-[oklch(0.769_0.188_70)]/80 border-[oklch(0.769_0.188_70)]/30" },
  2: { label: "action", className: "text-[oklch(0.705_0.213_47)] border-[oklch(0.705_0.213_47)]/30" },
  3: { label: "critical", className: "text-[oklch(0.645_0.246_16)] border-[oklch(0.645_0.246_16)]/30" },
};

export function RiskTierBadge({ tier, className }: { tier: number; className?: string }) {
  const config = riskConfig[tier];
  if (!config) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0 text-[10px] font-mono uppercase tracking-wider shrink-0",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
