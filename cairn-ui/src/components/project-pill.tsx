import { projectPillStyle } from "@/lib/colors";

export function ProjectPill({ name }: { name: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-1.5 py-0 text-[11px] font-medium shrink-0"
      style={projectPillStyle(name)}
    >
      {name}
    </span>
  );
}
