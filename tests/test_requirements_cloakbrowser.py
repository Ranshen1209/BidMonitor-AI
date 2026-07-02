import os, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RequirementsTests(unittest.TestCase):
    def test_cloakbrowser_listed_in_both_requirements(self):
        for rel in ("requirements.txt", "server/requirements.txt"):
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read().lower()
            self.assertIn("cloakbrowser", text, f"{rel} 缺少 cloakbrowser")
            self.assertIn("selenium", text, f"{rel} 缺少 selenium")


if __name__ == "__main__":
    unittest.main()
