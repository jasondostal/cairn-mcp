"use client";

import * as React from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

export interface SingleSelectOption {
  value: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
}

interface SingleSelectProps {
  options: SingleSelectOption[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  searchable?: boolean;
  className?: string;
  disabled?: boolean;
}

export function SingleSelect({
  options,
  value,
  onValueChange,
  placeholder = "Select…",
  searchable,
  className,
  disabled,
}: SingleSelectProps) {
  const [open, setOpen] = React.useState(false);

  // Auto-enable search when >5 options
  const showSearch = searchable ?? options.length > 5;

  const selected = options.find((o) => o.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            "justify-between gap-1 font-normal min-w-[120px]",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <span className="truncate">
            {selected ? (
              <span className="flex items-center gap-1.5">
                {selected.icon && <selected.icon className="h-3.5 w-3.5 shrink-0" />}
                {selected.label}
              </span>
            ) : (
              placeholder
            )}
          </span>
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="p-0 w-[--radix-popover-trigger-width]" align="start" side="bottom">
        <Command>
          {showSearch && <CommandInput placeholder="Search…" />}
          <CommandList>
            <CommandEmpty>No matches.</CommandEmpty>
            <CommandGroup>
              {options.map((option) => {
                const Icon = option.icon;
                return (
                  <CommandItem
                    key={option.value}
                    value={option.label}
                    onSelect={() => {
                      onValueChange(option.value);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-3.5 w-3.5 shrink-0",
                        value === option.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                    {Icon && <Icon className="mr-1.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                    {option.label}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
