#!/usr/bin/env python3
"""Tests for cockpit.communities (listing, checklist progress, "not
deployed" detection) and cockpit.d1_client (counts, cached, no token)
against fixture files and a fake D1 API — nothing here touches the network
or the real ~/my_repos/salsa-social clone."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import communities, d1_client  # noqa: E402

INDEX_TS = """
import { karaoke } from './karaoke.ts';
import { sbk } from './sbk.ts';

export const COMMUNITIES = [sbk, karaoke];
"""

SBK_TS = """
export const sbk = {
  id: 1,
  slug: 'sbk',
  name: 'SBK Social',
  origin: 'https://sbksocial.com',
  hosts: ['sbksocial.com', 'www.sbksocial.com'],
  status: 'live',
  ingestion: 'faurax',
  features: {
    attendanceTaps: true,
    classes: true,
    welcomeHosts: true,
    map: true,
    cityPages: true,
    styleFilters: true,
  },
};
"""

KARAOKE_TS = """
export const karaoke = {
  id: 2,
  slug: 'karaoke',
  name: 'Karaoke nights',
  origin: 'https://karaokeparis.pages.dev',
  hosts: ['karaokeparis.pages.dev'],
  status: 'hidden',
  ingestion: 'manual',
  features: {
    attendanceTaps: false,
    classes: false,
    welcomeHosts: false,
    map: false,
    cityPages: false,
    styleFilters: false,
  },
};
"""

SBK_CHECKLIST = """\
# Launch checklist — SBK Social

## SEO

- [x] Titles and meta descriptions on every page
- [ ] Search Console verified (manual; allowed unchecked)

## AEO/GEO (AI answer engines)

- [x] `llms.txt` describes the site and links to its pages

## Performance budgets

- [x] JS <= 35 KB gzipped on /

## Accessibility

- [x] Lighthouse accessibility >= 95

## Analytics

- [x] Cloudflare Web Analytics enabled (manual)

## Hidden community (only for a `status: 'hidden'` community)

- [ ] Every page sends noindex, nofollow
"""

KARAOKE_CHECKLIST = """\
# Launch checklist — Karaoke nights

## SEO

- [ ] Titles and meta descriptions on every page

## Hidden community (only for a `status: 'hidden'` community)

- [x] Every page sends noindex, nofollow
- [x] robots.txt disallows everything and has no Sitemap: line
- [x] No sitemap.xml or llms.txt in the deployed output
"""

CI_YML = """\
jobs:
  build:
    steps:
      - run: npm run check-launch-checklist -- sbk=dist karaoke=dist-karaoke
      - run: npx wrangler pages deploy dist --project-name salsa-social --branch main
      - run: npx wrangler pages deploy dist-karaoke --project-name karaokeparis --branch main
"""


def write_fixture(root, checklists=True, ci=True, karaoke_wrangler=True):
    communities_dir = os.path.join(root, "src", "server", "communities")
    os.makedirs(communities_dir, exist_ok=True)
    with open(os.path.join(communities_dir, "index.ts"), "w") as f:
        f.write(INDEX_TS)
    with open(os.path.join(communities_dir, "sbk.ts"), "w") as f:
        f.write(SBK_TS)
    with open(os.path.join(communities_dir, "karaoke.ts"), "w") as f:
        f.write(KARAOKE_TS)

    if checklists:
        checklist_dir = os.path.join(root, "docs", "launch-checklists")
        os.makedirs(checklist_dir, exist_ok=True)
        with open(os.path.join(checklist_dir, "sbk.md"), "w") as f:
            f.write(SBK_CHECKLIST)
        with open(os.path.join(checklist_dir, "karaoke.md"), "w") as f:
            f.write(KARAOKE_CHECKLIST)

    if ci:
        workflows_dir = os.path.join(root, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        with open(os.path.join(workflows_dir, "ci.yml"), "w") as f:
            f.write(CI_YML)

    if karaoke_wrangler:
        with open(os.path.join(root, "wrangler.karaoke.toml"), "w") as f:
            f.write("name = \"karaokeparis\"\n")


class ListCommunitiesTests(unittest.TestCase):
    def test_lists_in_index_order_with_fields(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            result, error = communities.list_communities(root)
            self.assertEqual(error, "")
            self.assertEqual([c["slug"] for c in result], ["sbk", "karaoke"])
            sbk = result[0]
            self.assertEqual(sbk["id"], 1)
            self.assertEqual(sbk["name"], "SBK Social")
            self.assertEqual(sbk["origin"], "https://sbksocial.com")
            self.assertEqual(sbk["hosts"], ["sbksocial.com", "www.sbksocial.com"])
            self.assertEqual(sbk["status"], "live")
            self.assertEqual(sbk["ingestion"], "faurax")
            self.assertTrue(sbk["features"]["attendanceTaps"])
            self.assertFalse(result[1]["features"]["attendanceTaps"])

    def test_unreadable_file_reports_error_others_still_render(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            os.remove(os.path.join(root, "src", "server", "communities", "karaoke.ts"))
            result, error = communities.list_communities(root)
            self.assertEqual(error, "")
            self.assertEqual(result[0]["slug"], "sbk")
            self.assertEqual(result[0]["error"], "")
            self.assertIn("cannot read", result[1]["error"])
            self.assertIn("karaoke.ts", result[1]["error"])

    def test_missing_index_reports_error(self):
        with tempfile.TemporaryDirectory() as root:
            result, error = communities.list_communities(root)
            self.assertEqual(result, [])
            self.assertIn("index.ts", error)


class ChecklistProgressTests(unittest.TestCase):
    def test_live_community_counts_manual_item_as_not_missing(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            progress = communities.checklist_progress("sbk", "live", root)
            self.assertEqual(progress["required"], 6)
            self.assertEqual(progress["checked"], 5)
            self.assertEqual(progress["missing"], [])
            self.assertEqual(progress["needed_for_live"], 0)

    def test_hidden_community_progress_and_needed_for_live(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            progress = communities.checklist_progress("karaoke", "hidden", root)
            self.assertEqual(progress["required"], 3)
            self.assertEqual(progress["checked"], 3)
            self.assertEqual(progress["missing"], [])
            self.assertEqual(progress["needed_for_live"], 1)

    def test_missing_checklist_file_reports_error(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root, checklists=False)
            progress = communities.checklist_progress("sbk", "live", root)
            self.assertIn("cannot read", progress["error"])


class DeployStatusTests(unittest.TestCase):
    def test_default_community_deployed(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            status = communities.deploy_status("sbk", is_default=True, salsa_dir=root)
            self.assertTrue(status["deployed"])
            self.assertEqual(status["hand_steps"], [])

    def test_non_default_community_deployed_with_own_wrangler_file(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            status = communities.deploy_status("karaoke", is_default=False, salsa_dir=root)
            self.assertTrue(status["deployed"])

    def test_not_deployed_lists_hand_steps(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root, karaoke_wrangler=False)
            status = communities.deploy_status("karaoke", is_default=False, salsa_dir=root)
            self.assertFalse(status["deployed"])
            self.assertTrue(any("wrangler.karaoke.toml" in s for s in status["hand_steps"]))
            self.assertIn("a Cloudflare Pages project", status["hand_steps"])
            self.assertIn("its row in D1", status["hand_steps"])

    def test_missing_ci_yml_reports_error(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root, ci=False)
            status = communities.deploy_status("sbk", is_default=True, salsa_dir=root)
            self.assertFalse(status["deployed"])
            self.assertIn("cannot read", status["hand_steps"][0])


class OverviewTests(unittest.TestCase):
    def test_overview_combines_everything(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            result = communities.overview(root)
            self.assertEqual(result["error"], "")
            self.assertEqual(len(result["communities"]), 2)
            sbk = result["communities"][0]
            self.assertEqual(sbk["checklist"]["required"], 6)
            self.assertTrue(sbk["deploy"]["deployed"])


class D1ClientTests(unittest.TestCase):
    def setUp(self):
        d1_client._cache.clear()
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_no_token_answers_with_error_and_no_counts(self):
        os.environ.pop("CF_ACCOUNT_ID", None)
        os.environ.pop("CF_D1_READ_TOKEN", None)
        result = d1_client.counts(1)
        self.assertIsNone(result["members"])
        self.assertIsNone(result["events"])
        self.assertIn("CF_ACCOUNT_ID", result["error"])

    def test_fake_api_response_and_cache_hit(self):
        os.environ["CF_ACCOUNT_ID"] = "acct"
        os.environ["CF_D1_READ_TOKEN"] = "token"
        calls = []

        def fake_query(sql, params):
            calls.append((sql, params))
            if "community_profiles" in sql:
                return [{"n": 7}]
            return [{"n": 12, "last_ingest": "2026-11-18T00:00:00Z"}]

        result = d1_client.counts(1, query_fn=fake_query, now=0.0)
        self.assertEqual(result["members"], 7)
        self.assertEqual(result["events"], 12)
        self.assertEqual(result["last_ingest"], "2026-11-18T00:00:00Z")
        self.assertEqual(result["error"], "")
        self.assertEqual(len(calls), 2)

        # Within the TTL, the cached value is returned without calling again.
        result2 = d1_client.counts(1, query_fn=fake_query, now=1.0)
        self.assertEqual(result2, result)
        self.assertEqual(len(calls), 2)

        # Past the TTL, it calls again.
        d1_client.counts(1, query_fn=fake_query, now=d1_client.CACHE_TTL + 2.0)
        self.assertEqual(len(calls), 4)

    def test_failed_call_answers_with_error_and_is_not_cached(self):
        os.environ["CF_ACCOUNT_ID"] = "acct"
        os.environ["CF_D1_READ_TOKEN"] = "token"
        calls = [0]

        def flaky_query(sql, params):
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError("HTTP 500")
            if "community_profiles" in sql:
                return [{"n": 3}]
            return [{"n": 5, "last_ingest": None}]

        result = d1_client.counts(2, query_fn=flaky_query, now=0.0)
        self.assertIsNone(result["members"])
        self.assertIn("HTTP 500", result["error"])

        # Subsequent call within CACHE_TTL must retry instead of returning the cached error.
        result2 = d1_client.counts(2, query_fn=flaky_query, now=1.0)
        self.assertEqual(result2["members"], 3)
        self.assertEqual(result2["events"], 5)
        self.assertEqual(result2["error"], "")


if __name__ == "__main__":
    unittest.main()
