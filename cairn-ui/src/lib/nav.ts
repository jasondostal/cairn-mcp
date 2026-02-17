import {
  Activity,
  BarChart3,
  Clock,
  Search,
  FolderOpen,
  FileText,
  Network,
  Share2,
  ListTodo,
  Brain,
  Shield,
  PenLine,
  MessageCircle,
  Mail,
  Radio,
  Boxes,
  Terminal,
  Settings,
  Kanban,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: "Core",
    items: [
      { href: "/", label: "Dashboard", icon: Activity },
      { href: "/work-items", label: "Work Items", icon: Kanban },
      { href: "/tasks", label: "Tasks", icon: ListTodo },
      { href: "/search", label: "Search", icon: Search },
      { href: "/capture", label: "Capture", icon: PenLine },
    ],
  },
  {
    label: "Context",
    items: [
      { href: "/sessions", label: "Sessions", icon: Radio },
      { href: "/chat", label: "Chat", icon: MessageCircle },
      { href: "/timeline", label: "Timeline", icon: Clock },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/projects", label: "Projects", icon: FolderOpen },
      { href: "/docs", label: "Docs", icon: FileText },
      { href: "/rules", label: "Rules", icon: Shield },
      { href: "/graph", label: "Graph", icon: Share2 },
    ],
  },
  {
    label: "Deep Dive",
    items: [
      { href: "/clusters", label: "Clusters", icon: Network },
      { href: "/thinking", label: "Thinking", icon: Brain },
      { href: "/workspace", label: "Workspace", icon: Boxes },
    ],
  },
  {
    label: "Ops",
    items: [
      { href: "/messages", label: "Messages", icon: Mail },
      { href: "/terminal", label: "Terminal", icon: Terminal },
      { href: "/analytics", label: "Ops Log", icon: BarChart3 },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

// Flat list for backward compatibility
export const navItems: NavItem[] = navGroups.flatMap((g) => g.items);
