DEFAULT_NON_FOLLOW_REASON_TAGS = [
    "地域问题",
    "金额不合适",
    "项目类型不匹配",
    "资质不满足",
    "时间太紧",
    "信息不完整",
    "重复项目",
    "已过期",
    "其它",
]

FIT_STATUSES = {"pending", "fit", "not_fit"}
FOLLOW_DECISIONS = {"pending", "follow", "not_follow"}
URGENCIES = {"low", "medium", "high", "urgent"}
PROJECT_STAGES = {"lead", "screening", "following", "submitted", "ended"}


def validate_review_update(payload: dict, reason_tags: list[str]) -> dict:
    allowed = {}
    if "fit_status" in payload:
        value = payload["fit_status"]
        if value not in FIT_STATUSES:
            raise ValueError("invalid fit_status")
        allowed["fit_status"] = value
    if "follow_decision" in payload:
        value = payload["follow_decision"]
        if value not in FOLLOW_DECISIONS:
            raise ValueError("invalid follow_decision")
        allowed["follow_decision"] = value
    if "urgency" in payload:
        value = payload["urgency"]
        if value not in URGENCIES:
            raise ValueError("invalid urgency")
        allowed["urgency"] = value
        allowed["urgency_source"] = "manual"
    if "project_stage" in payload:
        value = payload["project_stage"]
        if value not in PROJECT_STAGES:
            raise ValueError("invalid project_stage")
        allowed["project_stage"] = value
    if "non_follow_reasons" in payload:
        reasons = payload.get("non_follow_reasons") or []
        if not isinstance(reasons, list):
            raise ValueError("non_follow_reasons must be a list")
        unknown = [reason for reason in reasons if reason not in reason_tags]
        if unknown:
            raise ValueError("unknown non_follow_reasons")
        allowed["non_follow_reasons"] = reasons
    if "review_notes" in payload:
        allowed["review_notes"] = str(payload.get("review_notes") or "")

    final_decision = allowed.get("follow_decision", payload.get("follow_decision"))
    final_reasons = allowed.get("non_follow_reasons", payload.get("non_follow_reasons", []))
    if final_decision == "not_follow" and not final_reasons:
        raise ValueError("non_follow_reasons required when follow_decision is not_follow")
    return allowed


def _first_non_empty(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def resolve_result_data(bid) -> dict:
    manual = getattr(bid, "manual_overrides", None) or {}
    ai = getattr(bid, "ai_extracted_data", None) or {}
    return {
        "id": getattr(bid, "id", None),
        "title": bid.title,
        "url": bid.url,
        "source": bid.source,
        "publish_date": bid.publish_date,
        "organization": _first_non_empty(manual.get("organization"), ai.get("organization"), bid.purchaser),
        "amount": _first_non_empty(manual.get("amount"), ai.get("amount"), getattr(bid, "amount", "")),
        "amount_unit": _first_non_empty(manual.get("amount_unit"), ai.get("amount_unit"), getattr(bid, "amount_unit", "")),
        "region": _first_non_empty(manual.get("region"), ai.get("region"), getattr(bid, "region", "")),
        "category": _first_non_empty(manual.get("category"), ai.get("category"), getattr(bid, "category", "")),
        "project_type": _first_non_empty(manual.get("project_type"), ai.get("project_type"), getattr(bid, "project_type", "")),
        "nature": _first_non_empty(manual.get("nature"), ai.get("nature"), getattr(bid, "nature", "")),
        "registration_deadline": _first_non_empty(manual.get("registration_deadline"), getattr(bid, "registration_deadline", "")),
        "submission_deadline": _first_non_empty(manual.get("submission_deadline"), getattr(bid, "submission_deadline", "")),
        "bid_opening_time": _first_non_empty(manual.get("bid_opening_time"), getattr(bid, "bid_opening_time", "")),
        "deadlines": _first_non_empty(manual.get("deadlines"), ai.get("deadlines"), []),
    }
