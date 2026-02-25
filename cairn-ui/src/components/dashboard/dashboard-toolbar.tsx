"use client";

import { useState } from "react";
import { Check, LayoutGrid, Pencil, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WidgetPicker } from "./widget-picker";

interface DashboardToolbarProps {
  isEditing: boolean;
  visibleWidgets: string[];
  onSetEditing: (editing: boolean) => void;
  onToggleWidget: (id: string) => void;
  onReset: () => void;
}

export function DashboardToolbar({
  isEditing,
  visibleWidgets,
  onSetEditing,
  onToggleWidget,
  onReset,
}: DashboardToolbarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <>
      <div className="flex items-center gap-1">
        {isEditing ? (
          <>
            <Button variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
              <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
              Widgets
            </Button>
            <Button variant="outline" size="sm" onClick={onReset}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              Reset
            </Button>
            <Button size="sm" onClick={() => onSetEditing(false)}>
              <Check className="mr-1.5 h-3.5 w-3.5" />
              Done
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={() => onSetEditing(true)}>
            <Pencil className="mr-1.5 h-3.5 w-3.5" />
            Edit
          </Button>
        )}
      </div>

      <WidgetPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        visibleWidgets={visibleWidgets}
        onToggle={onToggleWidget}
      />
    </>
  );
}
