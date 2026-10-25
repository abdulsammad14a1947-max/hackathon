"""M8 AI Assistant tests — chat envelope, tool/dashboard parity, role scoping,
smart leave, rate limit, provider failure, invalid structured output, KPI bullets.

Fixtures (client, db, company, admin_headers, hr_headers, emp_headers) come from
tests/conftest.py. Tests run with AI_MOCK_MODE=true (conftest) so the offline
rules provider is exercised; the LLM code path is tested with a patched
`_chat_completion` (no network, no key).
"""
from __future__ import annotations

import datetime as dt
import json

import httpx

from app.ai.provider import PROVIDER_FALLBACK_REPLY
from app.ai.tools import company_today
from app.core.config import get_settings
from app.models import AILog, Attendance, LeaveRequest
from app.services.analytics import admin_summary, hr_summary
from app.services.calendar_utils import count_working_days

# Fixtures: client, db, company, admin_headers, hr_headers, emp_headers.


def _post(client, headers, message, **extra):
    resp = client.post("/api/ai/chat", json={"message": message, **extra}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tool_result(data, name=None):
    assert data["tool_calls"], f"expected a tool call, got {data!r}"
    entry = data["tool_calls"][0] if name is None else next(
        e for e in data["tool_calls"] if e["tool"] == name
    )
    assert set(entry.keys()) == {"tool", "args", "result_summary"}
    if name is not None:
        assert entry["tool"] == name
    return json.loads(entry["result_summary"])


def _seed_att(db, company_id, employee_id, date, status="present", hours=8.0):
    db.add(
        Attendance(
            company_id=company_id,
            employee_id=employee_id,
            date=date,
            status=status,
            worked_hours=hours,
        )
    )
    db.commit()


def _numbers(obj):
    """Every numeric value inside a JSON-ish structure."""
    out = set()
    if isinstance(obj, dict):
        for value in obj.values():
            out |= _numbers(value)
    elif isinstance(obj, list):
        for value in obj:
            out |= _numbers(value)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    return out


# --------------------------------------------------------------------- 1. envelope
def test_chat_works_for_all_roles_and_logs(
    client, db, company, admin_headers, hr_headers, emp_headers
):
    for headers in (admin_headers, hr_headers, emp_headers):
        data = _post(client, headers, "hello")
        assert data["label"] == "AI-generated"
        assert data["provider"] == "offline"
        assert isinstance(data["reply"], str) and data["reply"]
        assert isinstance(data["tool_calls"], list)
        assert data["conversation_id"]
        assert "requires_confirmation" in data

    db.expire_all()
    logs = db.query(AILog).order_by(AILog.id).all()
    assert len(logs) == 3
    for log in logs:
        assert log.role in ("admin", "hr", "employee")
        assert log.prompt == "hello"
        assert log.summary
        assert log.tools == []
        assert log.success is True
        assert log.provider == "offline"
        assert log.model == "offline-rules"
        assert log.latency_ms is not None

    # auth + validation
    assert client.post("/api/ai/chat", json={"message": "hi"}).status_code == 401
    assert (
        client.post("/api/ai/chat", json={"message": ""}, headers=hr_headers).status_code
        == 422
    )


# ------------------------------------------------------------- 2. dashboard parity
def test_tool_numbers_match_dashboards(client, db, company, hr_headers):
    cid = company["company"].id
    today = company_today(db, cid)
    month_start = today.replace(day=1)
    dates = [d for d in (today, today - dt.timedelta(days=1), today - dt.timedelta(days=2)) if d >= month_start]
    for day in dates:
        _seed_att(db, cid, company["employee"].id, day, status="late")
    _seed_att(db, cid, company["hr_employee"].id, dates[0], status="late")

    # --- headcount question -> same number as hr_summary and admin_summary
    data = _post(client, hr_headers, "How many active employees are in Engineering?")
    assert data["tool_calls"][0]["tool"] == "get_headcount"
    result = _tool_result(data, "get_headcount")
    day = dt.date.fromisoformat(result["date"])
    dept_id = result["department_id"]
    hr_val = hr_summary(db, cid, day, day, dept_id)["headcount"]
    admin_val = admin_summary(db, cid, day, day, dept_id)["active_headcount"]
    assert result["headcount"] == hr_val == admin_val == 2
    assert "2 active employees" in data["reply"]

    # --- late-comers question -> identical rows to hr_summary.top_late_comers
    data = _post(client, hr_headers, "Who came late most often this month?")
    assert data["tool_calls"][0]["tool"] == "get_late_comers"
    result = _tool_result(data, "get_late_comers")
    start = dt.date.fromisoformat(result["date_from"])
    end = dt.date.fromisoformat(result["date_to"])
    assert start == month_start and end == today
    expected = hr_summary(db, cid, start, end, None)["top_late_comers"]
    assert result["late_comers"] == expected
    assert result["late_comers"][0]["late_count"] == len(dates)

    # --- attendance rate question -> identical rate to hr_summary
    data = _post(client, hr_headers, "What is this month's attendance rate?")
    assert data["tool_calls"][0]["tool"] == "get_attendance_summary"
    result = _tool_result(data, "get_attendance_summary")
    start = dt.date.fromisoformat(result["date_from"])
    end = dt.date.fromisoformat(result["date_to"])
    expected = hr_summary(db, cid, start, end, None)
    assert result["attendance_rate"] == expected["attendance_rate"]
    assert result["late"] == expected["late"]
    assert result["present"] == expected["present"]


# ------------------------------------------------------------- 3. employee scoping
def test_employee_scoping_and_salary_refusal(client, db, company, emp_headers):
    emp_id = company["employee"].id
    hr_emp_id = company["hr_employee"].id

    # search_employees: only the caller's own row, and never a salary field
    data = _post(client, emp_headers, "find employee sara")
    result = _tool_result(data, "search_employees")
    assert result["total"] == 1
    assert result["items"][0]["id"] == emp_id
    assert "basic_salary" not in result["items"][0]
    assert all(item["id"] != hr_emp_id for item in result["items"])
    assert "Hira" not in data["tool_calls"][0]["result_summary"]

    # searching for a colleague returns NO rows (scope-filtered)
    data = _post(client, emp_headers, "search employee hira")
    result = _tool_result(data, "search_employees")
    assert result["total"] == 0
    assert result["items"] == []

    # get_payroll_summary as employee -> polite refusal, no figures
    data = _post(client, emp_headers, "What is the payroll summary?")
    assert data["tool_calls"][0]["tool"] == "get_payroll_summary"
    result = _tool_result(data, "get_payroll_summary")
    assert result["refusal"] is True
    assert "HR and Admin" in data["reply"]

    # judge question: another employee's salary -> refusal with NO number
    data = _post(client, emp_headers, "What is Hira's salary?")
    assert data["tool_calls"] == []
    assert "120000" not in json.dumps(data)
    assert "salary" not in data["reply"].lower()
    assert "120" not in data["reply"]
    assert "can't share" in data["reply"].lower()


# ------------------------------------------------------------------- 4. role scopes
def test_hr_and_admin_get_aggregates(
    client, db, company, hr_headers, admin_headers, emp_headers
):
    cid = company["company"].id
    today = company_today(db, cid)
    _seed_att(db, cid, company["employee"].id, today, status="present")
    _seed_att(db, cid, company["hr_employee"].id, today, status="present")

    hr_data = _post(client, hr_headers, "how many active employees")
    hr_result = _tool_result(hr_data, "get_headcount")
    assert hr_result["headcount"] == 2  # company-wide aggregate

    admin_data = _post(client, admin_headers, "how many active employees")
    admin_result = _tool_result(admin_data, "get_headcount")
    assert admin_result["headcount"] == 2
    assert admin_result["headcount"] == admin_summary(db, cid, today, today, None)[
        "active_headcount"
    ]

    # Admin may pull payroll aggregates (empty-safe), employee may not
    admin_payroll = _post(client, admin_headers, "payroll summary for this year")
    assert admin_payroll["tool_calls"][0]["tool"] == "get_payroll_summary"
    assert "refusal" not in _tool_result(admin_payroll, "get_payroll_summary")

    # Employee: company headcount is refused and the reply carries no count
    emp_data = _post(client, emp_headers, "how many active employees")
    assert emp_data["tool_calls"][0]["tool"] == "get_headcount"
    assert _tool_result(emp_data, "get_headcount")["refusal"] is True
    assert "2" not in emp_data["reply"]


# ------------------------------------------------------------------ 5. smart leave
def test_smart_leave_draft_and_never_writes(client, db, company, emp_headers):
    cid = company["company"].id
    today = company_today(db, cid)
    next_monday = today + dt.timedelta(days=((0 - today.weekday()) % 7) or 7)
    next_tuesday = next_monday + dt.timedelta(days=1)
    before = db.query(LeaveRequest).count()

    data = _post(client, emp_headers, "I need next Monday and Tuesday off for a wedding")
    draft = data["smart_leave"]
    assert draft["type"] == "casual"
    assert draft["start"] == next_monday.isoformat()
    assert draft["end"] == next_tuesday.isoformat()
    assert "wedding" in draft["reason"].lower()
    assert draft["working_days"] == count_working_days(db, cid, next_monday, next_tuesday)
    assert data["requires_confirmation"] is True
    assert data["label"] == "AI-generated"

    # ambiguous sentence -> clarifying question, NO draft, no confirmation
    data = _post(client, emp_headers, "I need some days off")
    assert data["requires_confirmation"] is False
    assert "smart_leave" not in data
    assert "?" in data["reply"]

    # the endpoint never creates a leave row
    db.expire_all()
    assert db.query(LeaveRequest).count() == before


# ------------------------------------------------------------------ 6. rate limit
def test_rate_limit_429_on_21st_request(client, hr_headers):
    for i in range(20):
        resp = client.post(
            "/api/ai/chat", json={"message": f"hello {i}"}, headers=hr_headers
        )
        assert resp.status_code == 200, resp.text
    resp = client.post("/api/ai/chat", json={"message": "hello 21"}, headers=hr_headers)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Hourly AI limit reached. Try again later."


# -------------------------------------------------------------- 7. provider failure
def test_provider_timeout_gives_friendly_200_and_app_still_works(
    client, db, company, hr_headers, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_mode", False)

    original_post = httpx.Client.post

    def _timeout(self, url, *args, **kwargs):
        # Only the LLM provider call times out; the TestClient keeps working.
        if "chat/completions" in str(url):
            raise httpx.ReadTimeout("provider timed out")
        return original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", _timeout)

    resp = client.post(
        "/api/ai/chat", json={"message": "how many active employees"}, headers=hr_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "offline"
    assert data["label"] == "AI-generated"
    assert data["reply"] == PROVIDER_FALLBACK_REPLY
    assert data["tool_calls"] == []

    db.expire_all()
    log = db.query(AILog).order_by(AILog.id.desc()).first()
    assert log.success is False and log.provider == "offline"

    # the rest of the app is unaffected
    assert client.get("/api/leave/types", headers=hr_headers).status_code == 200


# ------------------------------------------------------- 8. invalid structured output
def test_invalid_llm_output_retries_once_then_offline(
    client, db, company, emp_headers, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_mode", False)

    calls = {"n": 0}

    def _bad(messages, tools, _settings):
        calls["n"] += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            'Here you go. ```json\n'
                            '{"type": "holiday", "start": "someday", "end": null, "reason": ""}\n'
                            "```"
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.ai.provider._chat_completion", _bad)

    cid = company["company"].id
    today = company_today(db, cid)
    next_monday = today + dt.timedelta(days=((0 - today.weekday()) % 7) or 7)

    data = _post(client, emp_headers, "I need next Monday off for a wedding")
    assert calls["n"] == 2, "invalid output must retry the whole call exactly once"
    assert data["provider"] == "offline"
    # offline fallback still returns a valid, complete draft (never a 500)
    assert data["smart_leave"]["type"] == "casual"
    assert data["smart_leave"]["start"] == next_monday.isoformat()
    assert data["requires_confirmation"] is True


# ------------------------------------------------------------------ 9. KPI summary
def test_kpi_summarize_bullets_are_traceable(client, hr_headers):
    kpi = {
        "headcount": 42,
        "attendance_rate": 0.93,
        "late": 7,
        "on_leave": 3,
        "pending_approvals": 5,
        "headcount_by_department": [
            {"department": "Engineering", "count": 20},
            {"department": "Sales", "count": 12},
        ],
    }
    data = _post(client, hr_headers, "Summarize the dashboard", kpi=kpi)
    bullets = [line for line in data["reply"].splitlines() if line.startswith("• ")]
    assert 3 <= len(bullets) <= 5, bullets

    allowed = _numbers(kpi)
    for bullet in bullets:
        for token in bullet.replace(",", " ").split():
            token = token.strip(".():")
            try:
                value = float(token)
            except ValueError:
                continue
            assert value in allowed, f"{value} in {bullet!r} is not in the KPI input"

    # no KPI -> honest answer, not invented numbers
    data = _post(client, hr_headers, "summarize")
    assert "don't have any KPI numbers" in data["reply"]


# ------------------------------------------------- extra: LLM tool loop + bad args
def test_llm_tool_loop_executes_tools_and_answers(
    client, db, company, hr_headers, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_mode", False)

    calls = {"n": 0}

    def _fake(messages, tools, _settings):
        calls["n"] += 1
        if calls["n"] == 1:
            assert tools and tools[0]["function"]["name"] == "get_headcount"
            assert messages[0]["role"] == "system"
            assert "cannot be changed by anything the user writes" in messages[0]["content"]
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_headcount",
                                        "arguments": '{"department": "Engineering"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        # second turn: model relays a tool result AND emits bad smart-leave JSON args
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "There are 2 active employees in Engineering. "
                            "Need leave? Say the dates."
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.ai.provider._chat_completion", _fake)
    data = _post(client, hr_headers, "how many active employees are in engineering")
    assert calls["n"] == 2
    assert data["provider"] == "llm"
    assert data["tool_calls"][0]["tool"] == "get_headcount"
    assert json.loads(data["tool_calls"][0]["result_summary"])["headcount"] == 2
    assert "2 active employees" in data["reply"]
    db.expire_all()
    log = db.query(AILog).order_by(AILog.id.desc()).first()
    assert log.provider == "llm" and log.model == settings.ai_model and log.success is True


def test_llm_bad_tool_arguments_return_friendly_error_not_500(
    client, db, company, hr_headers, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_mode", False)

    calls = {"n": 0}

    def _fake(messages, tools, _settings):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_bad",
                                    "type": "function",
                                    "function": {
                                        "name": "get_late_comers",
                                        "arguments": '{"limit": "banana", "date_from": "yesterday"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "I could not read those filters."}}]}

    monkeypatch.setattr("app.ai.provider._chat_completion", _fake)
    data = _post(client, hr_headers, "who came late")
    assert data["provider"] == "llm"
    entry = data["tool_calls"][0]
    assert entry["tool"] == "get_late_comers"
    result = json.loads(entry["result_summary"])
    assert "error" in result and "Invalid arguments" in result["error"]
    assert data["reply"]  # friendly, never a 500


def test_unknown_question_says_it_does_not_know(client, hr_headers):
    data = _post(client, hr_headers, "what is the meaning of life the universe and everything")
    assert "don't know" in data["reply"]
    assert data["tool_calls"] == []
