import {
  Building2,
  CalendarRange,
  CheckSquare,
  Handshake,
  LayoutDashboard,
  Magnet,
  Settings,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/assistant", label: "Assistant", icon: Sparkles },
  { to: "/leads", label: "Leads", icon: Magnet },
  { to: "/deals", label: "Deals", icon: Handshake },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/contacts", label: "Contacts", icon: UsersRound },
  { to: "/activities", label: "Activities", icon: CalendarRange },
  { to: "/tasks", label: "Tasks", icon: CheckSquare },
];

export const SECONDARY_NAV: NavItem[] = [{ to: "/settings", label: "Settings", icon: Settings }];

export function isActive(pathname: string, to: string) {
  return to === "/" ? pathname === "/" : pathname === to || pathname.startsWith(`${to}/`);
}
