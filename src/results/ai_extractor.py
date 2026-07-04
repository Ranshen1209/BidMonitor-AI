from __future__ import annotations

import json
import re
from datetime import datetime

try:
    import requests
except ImportError:  # pragma: no cover
    class _RequestsShim:
        post = None

    requests = _RequestsShim()

try:
    from .detail_fetcher import fetch_detail_text
except ImportError:  # pragma: no cover
    from detail_fetcher import fetch_detail_text


DEADLINE_COLUMN_MAP = {
    "registration_deadline": ("registration_deadline", "end_at"),
    "submission_deadline": ("submission_deadline", "end_at"),
    "bid_opening_time": ("bid_opening_time", "start_at"),
}

URGENCY_REFERENCE_TYPES = {
    "submission_deadline": "submission",
    "registration_deadline": "registration",
    "bid_opening_time": "opening",
}


class AIExtractor:
    def __init__(self, config: dict | None):
        self.config = config or {}

    def _endpoint_url(self) -> str:
        base_url = (self.config.get("base_url") or "").rstrip("/")
        endpoint_type = self.config.get("endpoint_type") or "responses"
        if endpoint_type == "responses" and base_url.endswith("/v1"):
            return f"{base_url}/responses"
        if endpoint_type == "chat_completions" and base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return base_url

    def _build_prompt(self, title: str, url: str, source: str, publish_date: str, summary: str, detail_text: str) -> str:
        return (
            "请从以下招标信息中提取结构化字段，并严格只返回 JSON 对象。"
            "不要输出解释、不要输出 Markdown。"
            "deadlines 必须是数组，元素 type 仅允许 registration_deadline、submission_deadline、bid_opening_time。"
            "时间字段使用 YYYY-MM-DD HH:MM，未知则留空字符串。"
            "字段建议包含 organization, amount, amount_unit, region, category, project_type, nature, ai_recommendation, deadlines。\n\n"
            f"title: {title}\n"
            f"url: {url}\n"
            f"source: {source}\n"
            f"publish_date: {publish_date}\n"
            f"summary: {summary}\n"
            f"detail_text:\n{detail_text}"
        )

    def _parse_json_text(self, text: str) -> dict:
        if not isinstance(text, str):
            raise ValueError("AI response text is missing")
        if not text.strip():
            raise ValueError("AI response text is missing")
        cleaned = self._extract_json_object_text(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("AI response is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("AI response JSON must be an object")
        return data

    def _extract_json_object_text(self, text: str) -> str:
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        if "{" in cleaned and "}" in cleaned:
            return cleaned[cleaned.find("{"):cleaned.rfind("}") + 1].strip()
        return cleaned

    def extract(self, title: str, url: str, source: str, publish_date: str, summary: str, detail_text: str) -> dict:
        if not hasattr(requests, "post"):
            raise RuntimeError("requests is not installed")
        endpoint_type = self.config.get("endpoint_type") or "responses"
        endpoint_url = self._endpoint_url()
        prompt = self._build_prompt(title, url, source, publish_date, summary, detail_text)
        headers = {
            "Authorization": f"Bearer {self.config.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        if endpoint_type == "chat_completions":
            payload = {
                "model": self.config.get("model"),
                "stream": False,
                "messages": [
                    {"role": "system", "content": "You extract procurement data and reply with strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
            }
        else:
            payload = {
                "model": self.config.get("model"),
                "input": prompt,
            }

        response = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()
        if endpoint_type == "chat_completions":
            text = (((body.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
        else:
            text = body.get("output_text", "")
        return self._parse_json_text(text)

    def test_connection(self, prompt: str = "Reply with exactly: ok") -> str:
        if not hasattr(requests, "post"):
            raise RuntimeError("requests is not installed")
        endpoint_type = self.config.get("endpoint_type") or "responses"
        endpoint_url = self._endpoint_url()
        headers = {
            "Authorization": f"Bearer {self.config.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        if endpoint_type == "chat_completions":
            payload = {
                "model": self.config.get("model"),
                "stream": False,
                "messages": [
                    {"role": "system", "content": "Reply concisely to confirm connectivity."},
                    {"role": "user", "content": prompt},
                ],
            }
        else:
            payload = {
                "model": self.config.get("model"),
                "input": prompt,
            }

        response = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()
        if endpoint_type == "chat_completions":
            text = (((body.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
        else:
            text = body.get("output_text", "")
        return str(text).strip()


def _iter_deadline_dicts(ai_data: dict):
    deadlines = (ai_data or {}).get("deadlines") or []
    if isinstance(deadlines, dict):
        deadlines = [deadlines]
    if not isinstance(deadlines, list):
        return
    for deadline in deadlines:
        if isinstance(deadline, dict):
            yield deadline


def build_column_updates(ai_data: dict) -> dict:
    columns = {}
    for key in ["amount", "amount_unit", "region", "category", "project_type", "nature", "ai_recommendation"]:
        value = (ai_data or {}).get(key)
        if value:
            if key == "ai_recommendation" and isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif key == "ai_recommendation" and not isinstance(value, str):
                value = str(value)
            columns[key] = value

    used_deadlines = False
    for deadline in _iter_deadline_dicts(ai_data):
        deadline_type = deadline.get("type")
        mapping = DEADLINE_COLUMN_MAP.get(deadline_type)
        if not mapping:
            continue
        column_name, field_name = mapping
        value = deadline.get(field_name) or deadline.get("end_at") or deadline.get("start_at") or ""
        if value:
            columns[column_name] = value
            used_deadlines = True
    if used_deadlines:
        columns["deadline_source"] = "ai"
    return columns


def _parse_deadline_value(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def suggest_urgency(ai_data: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    deadlines = list(_iter_deadline_dicts(ai_data))
    priority = ["submission_deadline", "registration_deadline", "bid_opening_time"]

    chosen_type = None
    chosen_time = None
    for deadline_type in priority:
        for deadline in deadlines:
            if deadline.get("type") != deadline_type:
                continue
            candidate = _parse_deadline_value(
                deadline.get("end_at") or deadline.get("start_at") or ""
            )
            if candidate is not None:
                chosen_type = deadline_type
                chosen_time = candidate
                break
        if chosen_time is not None:
            break

    if chosen_time is None:
        return {}

    delta_days = (chosen_time - now).total_seconds() / 86400
    if delta_days <= 3:
        urgency = "urgent"
    elif delta_days <= 7:
        urgency = "high"
    elif delta_days <= 14:
        urgency = "medium"
    else:
        urgency = "low"

    return {
        "urgency": urgency,
        "urgency_source": "auto",
        "urgency_reference_time": chosen_time.strftime("%Y-%m-%d %H:%M"),
        "urgency_reference_type": URGENCY_REFERENCE_TYPES.get(chosen_type, chosen_type or ""),
    }


def enrich_new_bid(storage, result_id: int, bid, ai_config: dict | None, log_callback=None, fetch_config: dict | None = None) -> None:
    log = log_callback or (lambda _message: None)
    ok, detail_text, detail_error = fetch_detail_text(bid.url, fetch_config=fetch_config)
    if not ok:
        storage.update_detail_fetch(result_id, "failed", error=detail_error)
        storage.update_ai_extraction(
            result_id,
            "detail_fetch_failed",
            None,
            None,
            error=(detail_error or "")[:200],
        )
        return

    storage.update_detail_fetch(result_id, "success", detail_text=detail_text)

    config = ai_config or {}
    if not config.get("enable") or not config.get("api_key"):
        storage.update_ai_extraction(result_id, "pending", None, None)
        return

    try:
        ai_data = AIExtractor(config).extract(
            bid.title,
            bid.url,
            bid.source,
            bid.publish_date,
            bid.content or "",
            detail_text,
        )
        columns = build_column_updates(ai_data)
        current_bid = storage.get_by_id(result_id) if hasattr(storage, "get_by_id") else bid
        if getattr(current_bid, "urgency_source", "") != "manual":
            columns.update(suggest_urgency(ai_data))
        storage.update_ai_extraction(result_id, "extracted", ai_data, columns)
    except Exception as exc:
        log(f"[WARN] AI extraction failed for result {result_id}: {exc}")
        storage.update_ai_extraction(result_id, "extract_failed", None, None, error=str(exc)[:200])
