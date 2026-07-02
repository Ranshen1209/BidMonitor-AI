from __future__ import annotations

import re


_LOG_ICON_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF]\ufe0f?")


def strip_log_icons(message: object) -> str:
    text = str(message)
    text = _LOG_ICON_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()
