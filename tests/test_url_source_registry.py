import json
import os
import tempfile
import unittest

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_registry import load_url_sources


class UrlSourceRegistryTests(unittest.TestCase):
    def test_json_registry_loads_enabled_sources_and_skips_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "url_sources.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    """
                    {
                      "version": 1,
                      "sources": [
                        {"id": "ccgp", "name": "中国政府采购网", "url": "https://www.ccgp.gov.cn/", "enabled": true},
                        {"id": "off", "name": "禁用站点", "url": "https://off.example/", "enabled": false}
                      ]
                    }
                    """
                )

            sources = load_url_sources(path)

            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].id, "ccgp")
            self.assertEqual(sources[0].name, "中国政府采购网")
            self.assertEqual(sources[0].url, "https://www.ccgp.gov.cn/")

    def test_bookmarks_html_can_be_converted_to_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bookmarks.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    """
                    <!DOCTYPE NETSCAPE-Bookmark-file-1>
                    <DL><p>
                      <DT><A HREF="https://www.okcis.cn/">招标采购导航网</A>
                      <DT><A HREF="not-a-url">无效</A>
                      <DT><A HREF="https://www.okcis.cn/">重复</A>
                    </DL><p>
                    """
                )

            sources = load_url_sources(path)

            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].name, "招标采购导航网")
            self.assertEqual(sources[0].url, "https://www.okcis.cn/")

    def test_builtin_url_sources_all_have_site_topology_rules(self):
        sources_path = os.path.join(ROOT_DIR, "server", "url_sources.json")
        topologies_path = os.path.join(ROOT_DIR, "server", "site_topologies.json")

        source_ids = {source.id for source in load_url_sources(sources_path)}
        with open(topologies_path, "r", encoding="utf-8") as f:
            topology_payload = json.load(f)
        topology_by_id = {site["id"]: site for site in topology_payload["sites"]}

        self.assertEqual(source_ids, set(topology_by_id))
        for source_id in source_ids:
            with self.subTest(source_id=source_id):
                topology = topology_by_id[source_id]
                self.assertTrue(topology.get("allowed_hosts"))
                self.assertTrue(topology.get("seed_urls"))
                self.assertIn("detail_url_regex", topology)
                self.assertIn("list_url_regex", topology)

    def test_build_sources_filters_by_enabled_sites_and_merges_topology(self):
        from crawler.source_registry import build_sources

        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sources": [
                            {"id": "source-a", "name": "源 A", "url": "https://a.example/", "enabled": True},
                            {"id": "source-b", "name": "源 B", "url": "https://b.example/", "enabled": True},
                            {"id": "source-off", "name": "禁用源", "url": "https://off.example/", "enabled": False},
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sites": [
                            {
                                "id": "source-a",
                                "name": "拓扑 A",
                                "entry_url": "https://a.example/",
                                "allowed_hosts": ["a.example"],
                                "seed_urls": ["https://a.example/notices/"],
                                "detail_url_regex": [r"/detail/\d+$"],
                                "list_url_regex": [r"/notices/?$"],
                            },
                            {
                                "id": "source-b",
                                "name": "拓扑 B",
                                "entry_url": "https://b.example/",
                                "allowed_hosts": ["b.example"],
                                "seed_urls": ["https://b.example/notices/"],
                            },
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )

            sources = build_sources(
                sources_path,
                topologies_path,
                enabled_site_ids=["source-a"],
                site_metadata={"source-a": {"display_name": "展示名 A", "note": "keep"}},
                defaults={"domain_delay": 3, "auth_cookies": [{"domain": "a.example", "cookie": "sid=1"}]},
            )

        self.assertEqual([source.id for source in sources], ["source-a"])
        self.assertEqual(sources[0].name, "展示名 A")
        self.assertEqual(sources[0].url, "https://a.example/")
        self.assertEqual(sources[0].topology["id"], "source-a")
        self.assertEqual(sources[0].metadata["note"], "keep")
        self.assertEqual(sources[0].rate_limit["domain_delay"], 3)
        self.assertEqual(sources[0].auth_cookies[0]["cookie"], "sid=1")

    def test_build_sources_empty_enabled_sites_keeps_enabled_registry_defaults(self):
        from crawler.source_registry import build_sources

        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sources": [
                            {"id": "source-a", "name": "源 A", "url": "https://a.example/", "enabled": True},
                            {"id": "source-off", "name": "禁用源", "url": "https://off.example/", "enabled": False},
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                json.dump({"sites": []}, f)

            sources = build_sources(sources_path, topologies_path, enabled_site_ids=[])

        self.assertEqual([source.id for source in sources], ["source-a"])
        self.assertEqual(sources[0].topology, {})


if __name__ == "__main__":
    unittest.main()
