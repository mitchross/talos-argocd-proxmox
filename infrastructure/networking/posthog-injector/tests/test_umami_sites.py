"""Static checks for the Umami host allowlist and loader; no Docker needed (node is)."""

import hashlib
from pathlib import Path
import re
import subprocess
import unittest
import uuid


APP = Path(__file__).resolve().parents[1]
CONF = (APP / "default.conf").read_text()
SITES = APP / "umami-sites.map"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# sha256 of the PostHog replacement on main before Umami; changing PostHog means updating this on purpose.
POSTHOG_SHA256 = "be2dc6976d6799dbbb96d8136836380f420df9d8703a13e9c294a03184bc5486"


def entries():
    for line in SITES.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            yield line


class UmamiSitesTest(unittest.TestCase):
    def test_entries_are_real_uuids_on_injectable_hosts(self):
        never = set(re.findall(r"^\s+([a-z0-9.-]+) 0;$",
                               re.search(r"map \$host \$ph_host \{(.*?)\n\}", CONF, re.S).group(1), re.M))
        self.assertTrue({"umami.vanillax.me", "ingest-umami.vanillax.me", "radar.vanillax.me"} <= never)
        hosts = set()
        for line in entries():
            with self.subTest(line=line):
                m = re.fullmatch(r"((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)?vanillax\.me) (\S+);", line)
                self.assertIsNotNone(m, "expected '<host> <uuid>;'")
                host, site = m.groups()
                self.assertNotIn(host, never)
                self.assertFalse(host.startswith("ingest-"))
                self.assertNotIn(host, hosts, "duplicate host")
                hosts.add(host)
                parsed = uuid.UUID(site)
                self.assertEqual(str(parsed), site, "use the canonical lowercase UUID")
                self.assertEqual(parsed.variant, uuid.RFC_4122)
                self.assertNotEqual(parsed.int, 0)

    def test_umami_is_off_unless_listed(self):
        umami = re.search(r"map \$host \$umami_website_id \{(.*?)\n\}", CONF, re.S).group(1)
        self.assertEqual(umami.split(), ['default', '"";', 'include', '/etc/nginx/umami-sites.map;'])
        self.assertIn('\n    "" "";\n', re.search(r"map \$umami_website_id \$umami_snippet \{.*?\n\}", CONF, re.S).group(0))
        for path in (APP / "default.conf", APP / "README.md"):
            self.assertIsNone(UUID_RE.search(path.read_text()), f"{path.name} must not carry a website UUID")

    def test_posthog_replacement_is_unchanged(self):
        snippet = re.search(r"map \$host \$ph_snippet \{\n    default '(.*?)';\n\}", CONF, re.S).group(1)
        self.assertEqual(hashlib.sha256((snippet + "</head>").encode()).hexdigest(), POSTHOG_SHA256)
        self.assertEqual(re.findall(r"^\s*sub_filter\b.*$", CONF, re.M),
                         ["        sub_filter $ph_search '$ph_snippet$umami_snippet</head>';"])
        self.assertIn("sub_filter_once on;", CONF)

    def test_loader_behaviour(self):
        subprocess.run(["node", "--test", str(APP / "tests" / "umami_loader.test.cjs")], check=True)
