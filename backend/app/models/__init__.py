"""All ORM models — import this package to register every mapped class."""
from app.models.attendance import Attendance, AttendanceCorrection
from app.models.comms import AILog, Announcement, AuditLog, Notification
from app.models.company import (
    Company,
    CompanySettings,
    Department,
    Designation,
    Holiday,
    LeaveType,
)
from app.models.employee import Employee, User
from app.models.face import (
    EmployeeFaceTemplate,
    FaceChallenge,
    FaceVerificationEvent,
)
from app.models.leave import LeaveRequest
from app.models.payroll import PayrollItem, PayrollRun, SalaryStructure

__all__ = [
    "AILog",
    "Announcement",
    "Attendance",
    "AttendanceCorrection",
    "AuditLog",
    "Company",
    "CompanySettings",
    "Department",
    "Designation",
    "Employee",
    "EmployeeFaceTemplate",
    "FaceChallenge",
    "FaceVerificationEvent",
    "Holiday",
    "LeaveRequest",
    "LeaveType",
    "Notification",
    "PayrollItem",
    "PayrollRun",
    "SalaryStructure",
    "User",
]
