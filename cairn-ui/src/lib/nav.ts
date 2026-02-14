import {
  Activity,
  BarChart3,
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
  PenLine,
  MessageCircle,
  Mail,
  Radio,
  Terminal,
  Settings,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const navItems: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/capture", label: "Capture", icon: PenLine },
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
  { href: "/terminal", label: "Terminal", icon: Terminal },
  { href: "/analytics", label: "Ops Log", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];
