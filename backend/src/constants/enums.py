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
    # 跨学院签到时段重叠且未赢得唯一计薪资格，等待学院管理员裁决。
    ADJUDICATION_PENDING = "adjudication_pending"


class AdjudicationCaseStatus(str, Enum):
    PENDING = "pending"
    DECIDED = "decided"

class ApprovalSheetStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
