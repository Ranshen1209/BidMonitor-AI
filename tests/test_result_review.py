import unittest

from src.database.storage import BidInfo
from src.results.review import (
    DEFAULT_NON_FOLLOW_REASON_TAGS,
    resolve_result_data,
    validate_review_update,
)


class ResultReviewTests(unittest.TestCase):
    def test_default_non_follow_reason_tags_include_required_business_reasons(self):
        for tag in ["地域问题", "金额不合适", "项目类型不匹配", "资质不满足", "时间太紧", "信息不完整", "重复项目", "已过期", "其它"]:
            self.assertIn(tag, DEFAULT_NON_FOLLOW_REASON_TAGS)

    def test_validate_review_update_rejects_not_follow_without_reason(self):
        with self.assertRaises(ValueError) as ctx:
            validate_review_update(
                {"follow_decision": "not_follow", "non_follow_reasons": []},
                DEFAULT_NON_FOLLOW_REASON_TAGS,
            )

        self.assertIn("non_follow_reasons", str(ctx.exception))

    def test_validate_review_update_rejects_unknown_enum_and_reason(self):
        with self.assertRaises(ValueError):
            validate_review_update({"urgency": "now"}, DEFAULT_NON_FOLLOW_REASON_TAGS)

        with self.assertRaises(ValueError):
            validate_review_update(
                {"follow_decision": "not_follow", "non_follow_reasons": ["未知原因"]},
                DEFAULT_NON_FOLLOW_REASON_TAGS,
            )

    def test_validate_review_update_normalizes_valid_payload(self):
        normalized = validate_review_update(
            {
                "fit_status": "not_fit",
                "follow_decision": "not_follow",
                "urgency": "urgent",
                "project_stage": "screening",
                "non_follow_reasons": ["地域问题"],
                "review_notes": "外地项目",
            },
            DEFAULT_NON_FOLLOW_REASON_TAGS,
        )

        self.assertEqual(normalized["urgency_source"], "manual")
        self.assertEqual(normalized["non_follow_reasons"], ["地域问题"])

    def test_resolve_result_data_prefers_manual_then_ai_then_original(self):
        bid = BidInfo(
            title="原始标题",
            url="https://example.com/a",
            publish_date="2026-07-01",
            source="源",
            purchaser="原始采购人",
        )
        bid.ai_extracted_data = {
            "organization": "AI单位",
            "amount": "80",
            "deadlines": [{"type": "submission_deadline", "end_at": "2026-07-04"}],
        }
        bid.manual_overrides = {"organization": "人工单位"}

        resolved = resolve_result_data(bid)

        self.assertEqual(resolved["organization"], "人工单位")
        self.assertEqual(resolved["amount"], "80")
        self.assertEqual(resolved["title"], "原始标题")
