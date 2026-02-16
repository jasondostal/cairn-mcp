"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Memory } from "@/lib/api";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Activity,
  BarChart3,
  Boxes,
  Clock,
  FileText,
  FolderOpen,
  Landmark,
  ListTodo,
  Brain,
  Mail,
  MessageCircle,
  Network,
  PenLine,
  Radio,
  Search,
  Settings,
  Share2,
  Shield,
  Terminal,
} from "lucide-react";

const pages = [
  { href: "/capture", label: "New Capture", icon: PenLine },
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/messages", label: "Messages", icon: Mail },
  { href: "/sessions", label: "Sessions", icon: Radio },
  { href: "/timeline", label: "Timeline", icon: Clock },
  { href: "/cairns", label: "Cairns", icon: Landmark },
  { href: "/search", label: "Search", icon: Search },
  { href: "/projects", label: "Projects", icon: FolderOpen },
  { href: "/docs", label: "Docs", icon: FileText },
  { href: "/clusters", label: "Clusters", icon: Network },
  { href: "/graph", label: "Graph", icon: Share2 },
  { href: "/tasks", label: "Tasks", icon: ListTodo },
  { href: "/thinking", label: "Thinking", icon: Brain },
  { href: "/rules", label: "Rules", icon: Shield },
  { href: "/workspace", label: "Workspace", icon: Boxes },
  { href: "/terminal", label: "Terminal", icon: Terminal },
  { href: "/analytics", label: "Ops Log", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[]>([]);
  const [searching, setSearching] = useState(false);
  const router = useRouter();
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const doSearch = useCallback((q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    api
      .search(q, { limit: "8" })
      .then((data) => setResults(data.items))
      .catch(() => setResults([]))
      .finally(() => setSearching(false));
  }, []);

  function handleValueChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  }

  function navigate(href: string) {
    setOpen(false);
    setQuery("");
    setResults([]);
    router.push(href);
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) {
          setQuery("");
          setResults([]);
        }
      }}
    >
      <CommandInput
        placeholder="Search memories or navigate..."
        value={query}
        onValueChange={handleValueChange}
      />
      <CommandList>
        <CommandEmpty>
          {searching ? "Searching..." : "No results found."}
        </CommandEmpty>

        <CommandGroup heading="Navigation">
          {pages.map(({ href, label, icon: Icon }) => (
            <CommandItem key={href} onSelect={() => navigate(href)}>
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </CommandItem>
          ))}
        </CommandGroup>

        {results.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Memories">
              {results.map((m) => (
                <CommandItem
                  key={m.id}
                  onSelect={() => navigate(`/memories/${m.id}`)}
                >
                  <FileText className="mr-2 h-4 w-4" />
                  <div className="flex flex-col gap-0.5 overflow-hidden">
                    <span className="truncate text-sm">
                      {m.summary || m.content.slice(0, 80)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      #{m.id} &middot; {m.memory_type} &middot; {m.project}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
