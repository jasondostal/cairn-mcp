import { Card, CardContent } from "@/components/ui/card";

export function WidgetSkeleton() {
  return (
    <Card className="h-full">
      <CardContent className="flex h-full items-center justify-center">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      </CardContent>
    </Card>
  );
}
