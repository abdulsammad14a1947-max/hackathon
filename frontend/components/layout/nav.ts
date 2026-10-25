import type { Role } from "@/types/api";

export interface NavItem {
  label: string;
  href: string;
  icon: string;
  roles: Role[];
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: "dashboard", roles: ["admin", "hr", "employee"] },
  { label: "Employees", href: "/employees", icon: "employees", roles: ["admin", "hr"] },
  { label: "Attendance", href: "/attendance", icon: "attendance", roles: ["admin", "hr", "employee"] },
  { label: "Camera check-in", href: "/camera", icon: "camera", roles: ["admin", "hr", "employee"] },
  { label: "Leave", href: "/leave", icon: "leave", roles: ["admin", "hr", "employee"] },
  { label: "Payroll", href: "/payroll", icon: "payroll", roles: ["admin", "hr"] },
  { label: "Payslips", href: "/payslips", icon: "payslips", roles: ["employee"] },
  { label: "Announcements", href: "/announcements", icon: "announcements", roles: ["admin", "hr", "employee"] },
  { label: "AI Assistant", href: "/assistant", icon: "assistant", roles: ["admin", "hr", "employee"] },
  { label: "Settings", href: "/settings", icon: "settings", roles: ["admin", "hr"] },
  { label: "Audit log", href: "/audit", icon: "audit", roles: ["admin"] },
];

export const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/employees": "Employees",
  "/attendance": "Attendance",
  "/camera": "Camera check-in",
  "/leave": "Leave management",
  "/payroll": "Payroll",
  "/payslips": "Payslips",
  "/announcements": "Announcements",
  "/assistant": "AI Assistant",
  "/settings": "Settings",
  "/audit": "Audit log",
};

export function pageTitle(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.startsWith("/payroll/")) return "Payroll run";
  if (pathname.startsWith("/employees/")) return "Employee profile";
  if (pathname.startsWith("/payslips/")) return "Payslip";
  return "HCM Lite";
}
