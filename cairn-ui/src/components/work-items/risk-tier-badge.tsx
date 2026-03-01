import { cn } from "@/lib/utils";

const riskConfig: Record<number, { label: string; className: string }> = {
  1: { label: "caution", className: "text-status-wip/80 border-status-wip/30" },
  2: { label: "action", className: "text-priority-p4 border-priority-p4/30" },
  3: { label: "critical", className: "text-status-blocked border-status-blocked/30" },
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
