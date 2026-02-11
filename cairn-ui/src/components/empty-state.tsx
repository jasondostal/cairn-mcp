import { Inbox } from "lucide-react";

export function EmptyState({
  message,
  detail,
}: {
  message: string;
  detail?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground/50 mb-3" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {detail && (
        <p className="mt-1 text-xs text-muted-foreground/70">{detail}</p>
      )}
    </div>
  );
}
