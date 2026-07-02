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
        # build 阶段预下载 CloakBrowser 二进制(失败不阻断)
        self.assertIn("cloakbrowser", dockerfile)
        self.assertIn("|| true", dockerfile)


if __name__ == "__main__":
    unittest.main()
