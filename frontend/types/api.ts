/**
 * TypeScript interfaces mirroring the frozen API contract in docs/ARCHITECTURE.md §4.
 * Fields the backend may or may not include are optional so a shape change never
 * breaks the build — rendering falls back to honest "—" / empty states.
 */

export type Role = "admin" | "hr" | "employee";

export interface User {
  id: number;
  role: Role;
  full_name: string;
  email: string;
  employee_id?: number | null;
  must_change_password?: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type?: string;
  must_change_password: boolean;
  user: User;
}

export interface SetupStatus {
  needs_setup: boolean;
}

export interface SetupPayload {
  company_name: string;
  admin: { full_name: string; email: string; password: string };
}

export type EmploymentStatus = "active" | "inactive" | "terminated";

export interface Employee {
  id: number;
  employee_code: string;
  first_name: string;
  last_name: string;
  email: string;
  full_name?: string;
  phone?: string | null;
  address?: string | null;
  department_id?: number | null;
  designation_id?: number | null;
  department?: unknown;
  designation?: unknown;
  joining_date?: string;
  employment_status?: EmploymentStatus | string;
  gender?: "male" | "female" | "other" | null;
  basic_salary?: number | string | null;
  user_id?: number | null;
  user_role?: string | null;
  user_is_active?: boolean | null;
}

export interface Department {
  id: number;
  name: string;
}

export interface Designation {
  id: number;
  name: string;
}

export interface Holiday {
  id: number;
  name: string;
  date: string;
}

export interface LeaveType {
  id?: number;
  name: string;
  code: string;
  yearly_quota?: number | null;
  is_paid?: boolean;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type AttendanceStatus =
  | "present"
  | "late"
  | "half_day"
  | "missing_checkout"
  | "absent"
  | "on_leave"
  | "weekend"
  | "holiday";

export interface AttendanceRecord {
  id?: number;
  date: string;
  status: AttendanceStatus | string;
  check_in?: string | null;
  check_out?: string | null;
  worked_hours?: number | string | null;
  employee_id?: number;
  employee_code?: string;
  employee_name?: string;
  full_name?: string;
  department?: string;
  designation?: string;
}

export interface AttendanceMonthResponse {
  records?: AttendanceRecord[];
  items?: AttendanceRecord[];
  summary?: Record<string, number>;
}

export interface BoardRow extends AttendanceRecord {
  department?: string;
}

export interface Correction {
  id: number;
  attendance_date: string;
  requested_check_in: string;
  requested_check_out: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | string;
  review_comment?: string | null;
  reviewed_at?: string | null;
  employee_id?: number;
  employee_name?: string;
  employee_code?: string;
}

export type LeaveStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface LeaveRequest {
  id: number;
  leave_type_code?: string;
  leave_type?: unknown;
  start_date: string;
  end_date: string;
  working_days?: number | string;
  reason?: string;
  status: LeaveStatus | string;
  review_comment?: string | null;
  reviewed_at?: string | null;
  employee_id?: number;
  employee_name?: string;
  employee_code?: string;
  created_at?: string;
}

export interface LeaveBalanceItem {
  code: string;
  name: string;
  quota?: number | null;
  used?: number | string;
  pending?: number | string;
  remaining?: number | string;
  is_paid?: boolean;
}

export interface LeaveBalance {
  year?: number;
  items?: LeaveBalanceItem[];
}

export interface SalaryStructure {
  id: number;
  employee_id: number;
  employee_name?: string;
  employee_code?: string;
  basic_salary: number | string;
  effective_from: string;
  effective_to?: string | null;
}

export interface PayrollRun {
  id: number;
  period_year: number;
  period_month: number;
  status: "draft" | "finalized" | string;
  total_gross?: number | string;
  total_deductions?: number | string;
  total_net?: number | string;
  generated_at?: string;
  finalized_at?: string | null;
  item_count?: number;
}

export interface PayrollItem {
  id: number;
  run_id?: number;
  employee_id: number;
  employee_code?: string;
  employee_name?: string;
  basic: number | string;
  hra: number | string;
  medical: number | string;
  gross: number | string;
  working_days: number | string;
  present_days: number | string;
  absent_days: number | string;
  unpaid_leave_days: number | string;
  half_days: number | string;
  deduction_amount: number | string;
  tax: number | string;
  net_pay: number | string;
  note?: string | null;
}

export interface Payslip {
  id?: number;
  item_id?: number;
  period_year: number;
  period_month: number;
  gross?: number | string;
  net_pay?: number | string;
  tax?: number | string;
  deduction_amount?: number | string;
  employee_code?: string;
  employee_name?: string;
  status?: string;
}

export interface Announcement {
  id: number;
  title: string;
  body?: string;
  created_by?: number | null;
  created_by_name?: string;
  created_by_email?: string;
  created_at?: string;
  audience?: string;
  is_read?: boolean;
}

export interface Notification {
  id: number;
  title: string;
  body?: string | null;
  link?: string | null;
  is_read?: boolean;
  created_at?: string;
}

export interface AuditLog {
  id: number;
  actor_email?: string;
  action: string;
  entity_type: string;
  entity_id?: number | string | null;
  before?: unknown;
  after?: unknown;
  created_at?: string;
}

export interface CompanySettings {
  office_start_time?: string;
  grace_period_minutes?: number;
  weekend_days?: string[];
  office_lat?: number | null;
  office_lng?: number | null;
  geofence_radius_m?: number;
  timezone?: string;
  half_day_threshold_hours?: number;
}

export interface ChatToolCall {
  tool: string;
  args?: unknown;
  result_summary?: string;
}

export interface SmartLeave {
  type: string;
  start: string;
  end: string;
  reason: string;
  working_days?: number | string;
}

export interface ChatResponse {
  reply: string;
  tool_calls?: ChatToolCall[];
  smart_leave?: SmartLeave;
  requires_confirmation?: boolean;
  provider?: "llm" | "offline" | string;
  label?: string;
}

/* ---- analytics (server-computed, shapes normalised defensively in features/) ---- */

export interface AdminAnalytics {
  headcount?: number;
  attrition_ytd?: number | string;
  payroll_cost?: number | string;
  avg_salary?: number | string;
  headcount_by_department?: unknown;
  payroll_cost_by_department?: unknown;
  gender_breakdown?: unknown;
  tenure?: unknown;
  recent_audit?: unknown;
}

export interface HrAnalytics {
  headcount?: number;
  present?: number;
  late?: number;
  on_leave?: number;
  pending_approvals?: number;
  attendance_trend?: unknown;
  absenteeism_by_department?: unknown;
  leave_utilization?: unknown;
  top_late_comers?: unknown;
  insights?: unknown;
}

export interface EmployeeAnalytics {
  today_status?: unknown;
  week_hours?: unknown;
  late_count?: number;
  leave_balances?: unknown;
  recent_attendance?: unknown;
  last_payslip?: unknown;
  announcements?: unknown;
}
