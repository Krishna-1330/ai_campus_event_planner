from __future__ import annotations

from datetime import datetime
import uuid


def audit(store, action: str, event_id: str | None, details: str, actor="CampusFlow AI"):
    return store.insert("audit_logs", {"log_id": str(uuid.uuid4()), "timestamp": datetime.now().isoformat(timespec="seconds"), "action": action, "event_id": event_id, "actor": actor, "details": details})


def notify(store, title: str, message: str, event_id: str | None = None, level="info",
           recipient_resource_id: str | None = None, recipient_role: str | None = None):
    """Store an in-app operational notification or a member mailbox message.

    Messages without a recipient are administrative system notifications.  A
    resource-targeted message is visible only in that faculty member's or
    volunteer's mailbox.
    """
    return store.insert("notifications", {
        "notification_id": str(uuid.uuid4()), "created_at": datetime.now().isoformat(timespec="seconds"),
        "title": title, "message": message, "event_id": event_id, "level": level, "read": False,
        "recipient_resource_id": recipient_resource_id, "recipient_role": recipient_role,
    })
