"use client";

import * as React from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";

interface MultiSelectProps {
  options: Array<{ value: string; label: string }>;
  value: string[];
  onValueChange: (value: string[]) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  maxCount?: number;
  className?: string;
  hideSelectAll?: boolean;
}

export function MultiSelect({
  options,
  value,
  onValueChange,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  maxCount = 2,
  className,
  hideSelectAll = false,
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false);

  const selectedSet = React.useMemo(() => new Set(value), [value]);

  function toggleOption(optionValue: string) {
    const next = selectedSet.has(optionValue)
      ? value.filter((v) => v !== optionValue)
      : [...value, optionValue];
    onValueChange(next);
  }

  function toggleAll() {
    if (value.length === options.length) {
      onValueChange([]);
    } else {
      onValueChange(options.map((o) => o.value));
    }
  }

  function removeOption(optionValue: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    onValueChange(value.filter((v) => v !== optionValue));
  }

  function clearAll(e?: React.MouseEvent) {
    e?.stopPropagation();
    onValueChange([]);
  }

  const displayedBadges = value.slice(0, maxCount);
  const overflowCount = value.length - maxCount;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "justify-between gap-1 font-normal min-w-[120px]",
            className,
          )}
        >
          {value.length === 0 ? (
            <span className="text-muted-foreground">{placeholder}</span>
          ) : (
            <div className="flex items-center gap-1 overflow-hidden">
              {displayedBadges.map((v) => {
                const opt = options.find((o) => o.value === v);
                return (
                  <Badge
                    key={v}
                    variant="secondary"
                    className="text-xs px-1.5 py-0 h-5 shrink-0"
                  >
                    <span className="truncate max-w-[80px]">
                      {opt?.label ?? v}
                    </span>
                    <X
                      className="ml-0.5 h-3 w-3 cursor-pointer opacity-60 hover:opacity-100"
                      onClick={(e) => removeOption(v, e)}
                    />
                  </Badge>
                );
              })}
              {overflowCount > 0 && (
                <Badge
                  variant="secondary"
                  className="text-xs px-1.5 py-0 h-5 shrink-0"
                >
                  +{overflowCount}
                </Badge>
              )}
            </div>
          )}
          <div className="flex items-center shrink-0">
            {value.length > 0 && (
              <>
                <X
                  className="h-3.5 w-3.5 opacity-50 hover:opacity-100 cursor-pointer"
                  onClick={clearAll}
                />
                <Separator orientation="vertical" className="mx-1 h-4" />
              </>
            )}
            <ChevronsUpDown className="h-3.5 w-3.5 opacity-50" />
          </div>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="p-0 w-[200px]" align="start">
        <Command>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>No matches.</CommandEmpty>
            <CommandGroup>
              {!hideSelectAll && (
                <>
                  <CommandItem onSelect={toggleAll}>
                    <div
                      className={cn(
                        "mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary",
                        value.length === options.length
                          ? "bg-primary text-primary-foreground"
                          : "opacity-50",
                      )}
                    >
                      {value.length === options.length && (
                        <Check className="h-3 w-3" />
                      )}
                    </div>
                    <span className="text-sm">Select all</span>
                  </CommandItem>
                  <CommandSeparator />
                </>
              )}
              {options.map((option) => {
                const isSelected = selectedSet.has(option.value);
                return (
                  <CommandItem
                    key={option.value}
                    value={option.label}
                    onSelect={() => toggleOption(option.value)}
                  >
                    <div
                      className={cn(
                        "mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary",
                        isSelected
                          ? "bg-primary text-primary-foreground"
                          : "opacity-50",
                      )}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                    </div>
                    {option.label}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
          <CommandSeparator />
          <div className="p-1">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-center text-xs"
              onClick={() => setOpen(false)}
            >
              Close
            </Button>
          </div>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
