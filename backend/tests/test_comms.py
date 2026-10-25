"""M9 Communications & audit tests — announcements, notifications, audit log.

Fixtures: client, db, company, admin_headers, hr_headers, emp_headers.
"""
from __future__ import annotations

from app.models import AuditLog, Notification, User

# Fixtures (client, db, company, admin_headers, hr_headers, emp_headers) come
# from tests/conftest.py.


def _user_id(db, email: str) -> int:
    return db.query(User).filter(User.email == email).one().id


# --------------------------------------------------------------------- announcements
def test_employee_cannot_create_announcement(client, emp_headers):
    resp = client.post(
        "/api/announcements",
        json={"title": "Nope", "body": "from an employee"},
        headers=emp_headers,
    )
    assert resp.status_code == 403


def test_hr_creates_announcement_with_audit_and_notifications(
    client, db, company, hr_headers
):
    cid = company["company"].id
    resp = client.post(
        "/api/announcements",
        json={"title": "Town hall", "body": "Friday 3pm in the main hall."},
        headers=hr_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Town hall"
    assert body["audience"] == "all"
    assert body["created_by_name"] == "Hira HR"
    assert body["created_at"] is not None  # real timestamp, not a placeholder

    db.expire_all()
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.action == "announcement.created")
        .all()
    )
    assert len(audit) == 1
    assert audit[0].actor_email == "hr@acme.test"
    assert audit[0].entity_type == "announcement"
    assert audit[0].after["title"] == "Town hall"
    assert audit[0].created_at is not None

    # every employee-role user is notified (Sara yes, Hira is HR → no)
    notes = db.query(Notification).filter(Notification.title == "Town hall").all()
    sara_uid = _user_id(db, "sara@acme.test")
    hira_uid = _user_id(db, "hr@acme.test")
    assert [n.user_id for n in notes] == [sara_uid]
    assert notes[0].link == "/announcements"
    assert notes[0].created_at is not None
    assert notes[0].is_read is False

    # validation: empty title rejected
    bad = client.post(
        "/api/announcements", json={"title": "", "body": "x"}, headers=hr_headers
    )
    assert bad.status_code == 422


def test_list_announcements_newest_first_for_all_roles(
    client, db, company, hr_headers, admin_headers, emp_headers
):
    first = client.post(
        "/api/announcements",
        json={"title": "First", "body": "older one"},
        headers=hr_headers,
    )
    second = client.post(
        "/api/announcements",
        json={"title": "Second", "body": "newer one"},
        headers=admin_headers,
    )
    assert first.status_code == 201 and second.status_code == 201

    for headers in (emp_headers, hr_headers, admin_headers):
        resp = client.get("/api/announcements", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["page"] == 1
        titles = [i["title"] for i in data["items"]]
        assert titles == ["Second", "First"]  # newest first
        assert data["items"][0]["created_by_name"] is not None
        assert data["items"][0]["created_at"] is not None

    page = client.get("/api/announcements?page=1&page_size=1", headers=emp_headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1


def test_delete_announcement_admin_or_author_only(
    client, db, company, hr_headers, admin_headers, emp_headers
):
    x = client.post(
        "/api/announcements",
        json={"title": "By admin", "body": "admin-authored"},
        headers=admin_headers,
    ).json()
    y = client.post(
        "/api/announcements",
        json={"title": "By HR", "body": "hr-authored"},
        headers=hr_headers,
    ).json()

    # employee is neither admin nor author → 403
    assert (
        client.delete(f"/api/announcements/{y['id']}", headers=emp_headers).status_code
        == 403
    )
    # HR is not the author of the admin's post → 403
    assert (
        client.delete(f"/api/announcements/{x['id']}", headers=hr_headers).status_code
        == 403
    )
    # HR deleting own post → 204
    assert (
        client.delete(f"/api/announcements/{y['id']}", headers=hr_headers).status_code
        == 204
    )
    # Admin deleting any post → 204
    assert (
        client.delete(f"/api/announcements/{x['id']}", headers=admin_headers).status_code
        == 204
    )
    # unknown id → 404
    assert client.delete("/api/announcements/999999", headers=admin_headers).status_code == 404

    assert client.get("/api/announcements", headers=emp_headers).json()["total"] == 0
    db.expire_all()
    deletes = db.query(AuditLog).filter(AuditLog.action == "announcement.deleted").all()
    assert len(deletes) == 2  # both deletions audit-logged
    assert all(a.before is not None and a.created_at is not None for a in deletes)


# --------------------------------------------------------------------- notifications
def test_notification_unread_and_read_flow_own_only(
    client, db, company, emp_headers, hr_headers
):
    cid = company["company"].id
    sara_uid = _user_id(db, "sara@acme.test")
    hira_uid = _user_id(db, "hr@acme.test")
    sara_note = Notification(company_id=cid, user_id=sara_uid, title="For Sara")
    hira_note = Notification(company_id=cid, user_id=hira_uid, title="For Hira")
    db.add_all([sara_note, hira_note])
    db.commit()

    # unread counts are per-user
    assert client.get("/api/notifications/unread-count", headers=emp_headers).json() == {
        "count": 1
    }
    assert client.get("/api/notifications/unread-count", headers=hr_headers).json() == {
        "count": 1
    }

    # unread=true filter + real created_at
    inbox = client.get("/api/notifications?unread=true", headers=emp_headers).json()
    assert inbox["total"] == 1
    assert inbox["unread"] == 1
    assert inbox["items"][0]["title"] == "For Sara"
    assert inbox["items"][0]["is_read"] is False
    assert inbox["items"][0]["created_at"] is not None

    # marking read: only OWN ids are honoured even if foreign ids are sent
    resp = client.post(
        "/api/notifications/read",
        json={"ids": [sara_note.id, hira_note.id]},
        headers=emp_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"updated": 1}  # Hira's row was NOT touched

    assert client.get("/api/notifications/unread-count", headers=emp_headers).json() == {
        "count": 0
    }
    assert client.get("/api/notifications/unread-count", headers=hr_headers).json() == {
        "count": 1  # Hira's still unread
    }
    assert client.get("/api/notifications?unread=true", headers=emp_headers).json()[
        "items"
    ] == []

    # re-marking the same ids is a no-op
    again = client.post(
        "/api/notifications/read", json={"ids": [sara_note.id]}, headers=emp_headers
    )
    assert again.json() == {"updated": 0}


# --------------------------------------------------------------------- audit logs
def test_audit_logs_admin_only(client, hr_headers, emp_headers, admin_headers):
    assert client.get("/api/audit-logs", headers=hr_headers).status_code == 403
    assert client.get("/api/audit-logs", headers=emp_headers).status_code == 403

    resp = client.get("/api/audit-logs", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"items", "total", "page", "page_size"} <= set(data.keys())
    assert data["total"] >= len(data["items"]) >= 1  # at least the logins
    entry = data["items"][0]
    assert {"actor", "action", "entity_type", "created_at"} <= set(entry.keys())
    assert entry["created_at"] is not None
    # newest first
    times = [i["created_at"] for i in data["items"]]
    assert times == sorted(times, reverse=True)


def test_audit_log_filters_and_content(
    client, db, company, hr_headers, admin_headers
):
    client.post(
        "/api/announcements",
        json={"title": "Audit me", "body": "creates an audit row"},
        headers=hr_headers,
    )

    filtered = client.get(
        "/api/audit-logs?action=announcement.created", headers=admin_headers
    ).json()
    assert filtered["total"] == 1
    row = filtered["items"][0]
    assert row["actor"] == "hr@acme.test"
    assert row["action"] == "announcement.created"
    assert row["entity_type"] == "announcement"
    assert row["entity_id"] is not None
    assert row["created_at"] is not None

    by_entity = client.get(
        "/api/audit-logs?entity_type=user", headers=admin_headers
    ).json()
    assert by_entity["total"] >= 1  # logins
    assert all(i["entity_type"] == "user" for i in by_entity["items"])

    page_size = client.get(
        "/api/audit-logs?page=1&page_size=1", headers=admin_headers
    ).json()
    assert len(page_size["items"]) == 1
    assert page_size["total"] >= 2


def test_audit_logs_are_read_only_routes():
    """No endpoint anywhere may update/delete audit_logs (frozen rule §3)."""
    from app.main import app

    audit_routes = [
        r
        for r in app.routes
        if getattr(r, "path", "").startswith("/api/audit-logs")
    ]
    assert audit_routes, "audit-logs read endpoint must exist"
    allowed = {"GET", "HEAD", "OPTIONS"}
    for route in audit_routes:
        assert route.methods <= allowed, f"audit route exposes {route.methods}"
