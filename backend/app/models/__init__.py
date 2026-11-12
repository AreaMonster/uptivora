"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.base import Base
from app.models.billing import (
    BillingInterval,
    LicenseOrder,
    LicenseOrderStatus,
    LicenseProduct,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from app.models.monitors import (
    CheckResult,
    CheckRollup,
    HttpMethod,
    Incident,
    Monitor,
    MonitorStatus,
    PausedReason,
)
from app.models.notifications import (
    MAX_ALERT_CONTACTS,
    AlertContact,
    NotificationKind,
    NotificationOutbox,
    NotificationSettings,
    OutboxStatus,
)
from app.models.system import (
    AppSetting,
    AuditLog,
    InstalledLicense,
    RateLimitBucket,
    SystemEvent,
    WorkerHeartbeat,
)
from app.models.users import AuthToken, AuthTokenPurpose, Session, User, UserRole

__all__ = [
    "MAX_ALERT_CONTACTS",
    "AlertContact",
    "AppSetting",
    "AuditLog",
    "AuthToken",
    "AuthTokenPurpose",
    "Base",
    "BillingInterval",
    "CheckResult",
    "CheckRollup",
    "HttpMethod",
    "Incident",
    "InstalledLicense",
    "LicenseOrder",
    "LicenseOrderStatus",
    "LicenseProduct",
    "Monitor",
    "MonitorStatus",
    "NotificationKind",
    "NotificationOutbox",
    "NotificationSettings",
    "OutboxStatus",
    "PausedReason",
    "Payment",
    "PaymentStatus",
    "Plan",
    "RateLimitBucket",
    "Session",
    "Subscription",
    "SubscriptionStatus",
    "SystemEvent",
    "User",
    "UserRole",
    "WebhookEvent",
    "WorkerHeartbeat",
]
