import { AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function ErrorState({
  message = "Something went wrong.",
  detail,
}: {
  message?: string;
  detail?: string;
}) {
  return (
    <Card className="border-destructive/30">
      <CardContent className="flex items-center gap-3 p-4">
        <AlertCircle className="h-5 w-5 shrink-0 text-destructive" />
        <div>
          <p className="text-sm font-medium">{message}</p>
          {detail && (
            <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
