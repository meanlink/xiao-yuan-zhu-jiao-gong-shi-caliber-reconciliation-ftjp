from enum import Enum

class UserRole(str, Enum):
    TA = "ta"
    TEACHER = "teacher"
    COLLEGE_ADMIN = "college_admin"

class WorkRecordStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    MANUAL_REVIEW = "manual_review"
    APPROVED = "approved"
    REJECTED = "rejected"

class ApprovalSheetStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
