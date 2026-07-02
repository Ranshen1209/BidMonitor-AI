import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DockerPackagingTests(unittest.TestCase):
    def test_docker_packaging_files_exist_and_use_server_entrypoint(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("python:3.11-slim", dockerfile)
        self.assertIn("server/requirements.txt", dockerfile)
        self.assertIn("server/app.py", dockerfile)
        self.assertIn("8080", dockerfile)
        self.assertIn("bidmonitor", compose)
        self.assertIn("8080:8080", compose)

    def test_docker_context_excludes_local_runtime_data_and_external_materials(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        for pattern in ["data/", "logs/", ".venv/", "__pycache__/", ".git"]:
            self.assertIn(pattern, dockerignore)

        self.assertNotIn("/Users/cervine/Documents/Rule-Project", dockerfile)
        self.assertNotIn("bid_related_url_list.txt", dockerfile)


    def test_dockerfile_bundles_chromium_deps_and_prefetches_cloak(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for pkg in ["libnss3", "libgbm1", "libasound2", "libatk1.0-0", "fonts-liberation"]:
            self.assertIn(pkg, dockerfile)
        self.assertIn("BIDMONITOR_BROWSER_BINARIES=/app/.browser-binaries", dockerfile)
        self.assertIn("CLOAKBROWSER_CACHE_DIR=/app/.browser-binaries/cloakbrowser", dockerfile)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH=/app/.browser-binaries/playwright", dockerfile)
        self.assertIn("COPY .browser-binaries .browser-binaries", dockerfile)
        # build 阶段预下载 CloakBrowser 二进制(失败不阻断)
        self.assertIn("python -m cloakbrowser install", dockerfile)
        self.assertIn("|| true", dockerfile)

    def test_browser_binary_directory_is_git_ignored_but_sent_to_docker(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn(".browser-binaries/*", gitignore)
        self.assertIn("!.browser-binaries/.gitkeep", gitignore)
        self.assertIn("!.browser-binaries/README.md", gitignore)
        self.assertNotIn(".browser-binaries", dockerignore)


if __name__ == "__main__":
    unittest.main()
