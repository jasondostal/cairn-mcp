"use client";

import type { Rule } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ImportanceBadge } from "@/components/importance-badge";

interface RuleSheetProps {
  rule: Rule | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RuleSheet({ rule, open, onOpenChange }: RuleSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto">
        {rule && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {rule.project}
                </Badge>
                <ImportanceBadge importance={rule.importance} />
              </div>
              <SheetTitle className="text-base">
                Rule #{rule.id}
              </SheetTitle>
              <SheetDescription>
                {formatDateTime(rule.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              <Separator />

              <div>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Content
                </h3>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {rule.content}
                </p>
              </div>

              {rule.tags.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      Tags
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {rule.tags.map((t) => (
                        <Badge key={t} variant="secondary" className="text-xs">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <Separator />
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>ID: {rule.id}</p>
                <p>Created: {formatDateTime(rule.created_at)}</p>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
