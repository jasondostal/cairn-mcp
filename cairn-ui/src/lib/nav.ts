import {
  Activity,
  BarChart3,
  BookOpen,
  Search,
  FolderOpen,
  FileText,
  Network,
  Share2,
  Brain,
  Shield,
  PenLine,
  MessageCircle,
  Radio,
  Boxes,
  Terminal,
  Settings,
  Kanban,
  Eye,
  Users,
  Users2,
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
      { href: "/search", label: "Search", icon: Search },
      { href: "/capture", label: "Capture", icon: PenLine },
    ],
  },
  {
    label: "Context",
    items: [
      { href: "/sessions", label: "Sessions", icon: Radio },
      { href: "/chat", label: "Chat", icon: MessageCircle },
      { href: "/memories", label: "Memories", icon: BookOpen },
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
      { href: "/terminal", label: "Terminal", icon: Terminal },
      { href: "/analytics", label: "Ops Log", icon: BarChart3 },
      { href: "/watchtower", label: "Watchtower", icon: Eye },
      { href: "/admin/users", label: "Users", icon: Users },
      { href: "/admin/groups", label: "Groups", icon: Users2 },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

// Flat list for backward compatibility
export const navItems: NavItem[] = navGroups.flatMap((g) => g.items);
