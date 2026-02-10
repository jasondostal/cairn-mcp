import {
  Activity,
  Clock,
  Landmark,
  Search,
  FolderOpen,
  FileText,
  Network,
  Share2,
  ListTodo,
  Brain,
  Shield,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const navItems: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Activity },
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
];
