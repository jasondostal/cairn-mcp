import { Inbox, type LucideIcon } from "lucide-react";

export function EmptyState({
  message,
  detail,
  icon: Icon,
  title,
  description,
}: {
  message?: string;
  detail?: string;
  icon?: LucideIcon;
  title?: string;
  description?: string;
}) {
  const IconComponent = Icon ?? Inbox;
  const heading = title ?? message;
  const sub = description ?? detail;

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <IconComponent className="h-8 w-8 text-muted-foreground/50 mb-3" />
      {heading && <p className="text-sm text-muted-foreground">{heading}</p>}
      {sub && (
        <p className="mt-1 text-xs text-muted-foreground/70">{sub}</p>
      )}
    </div>
  );
}
