#!/usr/bin/env python3
"""Tests for cockpit.salsa_social_edit against a temporary git repo with a
fake `origin` remote and a stubbed check command - nothing here touches the
network, GitHub, or the real ~/my_repos/salsa-social clone."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import salsa_social_edit  # noqa: E402

KARAOKE_TS = """export const karaoke = {
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

KARAOKE_CHECKLIST = """\
## Hidden community (only for a `status: 'hidden'` community)

- [x] Every page sends noindex, nofollow
- [x] robots.txt disallows everything and has no Sitemap: line
- [x] No sitemap.xml or llms.txt in the deployed output
"""

INDEX_TS = """import { karaoke } from './karaoke.ts';
import type { Community } from './types';

export const COMMUNITIES: readonly Community[] = [karaoke];
"""

CHECKLIST_TEMPLATE = """# Launch checklist template

## SEO

- [ ] Titles and meta descriptions on every page
- [ ] Search Console verified (manual; allowed unchecked)

## Hidden community (only for a `status: 'hidden'` community)

- [ ] Every page sends `noindex, nofollow`
- [ ] `robots.txt` disallows everything and has no `Sitemap:` line
- [ ] No `sitemap.xml` or `llms.txt` in the deployed output
"""


def _run(args, cwd):
    done = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def ok_checks(repo_root, timeout):
    return True, "", ""


def failing_checks(name, output):
    def run(repo_root, timeout):
        return False, name, output
    return run


def make_repo(root):
    """A bare `origin` plus a clone of it, on `main`, with karaoke's config
    and checklist committed and pushed. Returns the clone's path."""
    origin = os.path.join(root, "origin.git")
    clone = os.path.join(root, "clone")
    os.makedirs(origin)
    _run(["init", "--bare", "-b", "main", origin], root)

    communities_dir = os.path.join(clone, "src", "server", "communities")
    checklist_dir = os.path.join(clone, "docs", "launch-checklists")
    docs_dir = os.path.join(clone, "docs")
    os.makedirs(communities_dir)
    os.makedirs(checklist_dir)
    with open(os.path.join(communities_dir, "karaoke.ts"), "w") as f:
        f.write(KARAOKE_TS)
    with open(os.path.join(communities_dir, "index.ts"), "w") as f:
        f.write(INDEX_TS)
    with open(os.path.join(checklist_dir, "karaoke.md"), "w") as f:
        f.write(KARAOKE_CHECKLIST)
    with open(os.path.join(docs_dir, "launch-checklist-template.md"), "w") as f:
        f.write(CHECKLIST_TEMPLATE)

    _run(["init", "-b", "main", clone], root)
    _run(["config", "user.email", "test@example.com"], clone)
    _run(["config", "user.name", "Test"], clone)
    _run(["remote", "add", "origin", origin], clone)
    _run(["add", "-A"], clone)
    _run(["commit", "-m", "initial"], clone)
    _run(["push", "-u", "origin", "main"], clone)
    return clone, origin


class EditCommunityTests(unittest.TestCase):
    def test_successful_edit_commits_and_pushes(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            result = salsa_social_edit.edit_community(
                "karaoke", {"ingestion": "faurax"}, {"ingestion": "manual"},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertTrue(result["ok"], result.get("message"))
            self.assertTrue(result["commit"])
            with open(os.path.join(clone, "src", "server", "communities", "karaoke.ts")) as f:
                self.assertIn("ingestion: 'faurax'", f.read())
            log = _run(["log", "--oneline", "-1"], origin)
            self.assertIn("karaoke: ingestion: manual -> faurax", log)

    def test_refused_bad_value_touches_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            before = _run(["rev-parse", "main"], origin)
            result = salsa_social_edit.edit_community(
                "karaoke", {"status": "deleted"}, {"status": "hidden"},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("status", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], origin))

    def test_refused_unknown_field(self):
        with tempfile.TemporaryDirectory() as root:
            clone, _origin = make_repo(root)
            result = salsa_social_edit.edit_community(
                "karaoke", {"slug": "renamed"}, {},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("unknown", result["message"])

    def test_nothing_changed_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            clone, _origin = make_repo(root)
            result = salsa_social_edit.edit_community(
                "karaoke", {"ingestion": "manual"}, {"ingestion": "manual"},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("nothing changed", result["message"])

    def test_refused_failing_check_restores_file_and_makes_no_commit(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            before = _run(["rev-parse", "main"], origin)
            with open(os.path.join(clone, "src", "server", "communities", "karaoke.ts")) as f:
                original_text = f.read()

            result = salsa_social_edit.edit_community(
                "karaoke", {"ingestion": "faurax"}, {"ingestion": "manual"},
                salsa_dir=clone, run_checks=failing_checks("npm test", "1 test failed"),
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("npm test", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], origin))
            with open(os.path.join(clone, "src", "server", "communities", "karaoke.ts")) as f:
                self.assertEqual(original_text, f.read())

    def test_switch_to_live_with_unticked_checklist_refused_before_push(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            before = _run(["rev-parse", "main"], origin)

            result = salsa_social_edit.edit_community(
                "karaoke", {"status": "live"}, {"status": "hidden"},
                salsa_dir=clone,
                run_checks=failing_checks(
                    "npm run check-launch-checklist",
                    "karaoke: unchecked required item: \"Titles and meta descriptions on every page\"",
                ),
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("check-launch-checklist", result["message"])
            self.assertIn("unchecked required item", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], origin))
            with open(os.path.join(clone, "src", "server", "communities", "karaoke.ts")) as f:
                self.assertIn("status: 'hidden'", f.read())

    def test_refused_failing_push_drops_local_commit(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            hook = os.path.join(origin, "hooks", "pre-receive")
            with open(hook, "w") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(hook, 0o755)
            before = _run(["rev-parse", "main"], clone)

            result = salsa_social_edit.edit_community(
                "karaoke", {"ingestion": "faurax"}, {"ingestion": "manual"},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("push failed", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], clone))
            with open(os.path.join(clone, "src", "server", "communities", "karaoke.ts")) as f:
                self.assertIn("ingestion: 'manual'", f.read())

    def test_refused_when_someone_else_pushed_since_page_loaded(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)

            other = os.path.join(root, "other")
            _run(["clone", origin, other], root)
            _run(["config", "user.email", "other@example.com"], other)
            _run(["config", "user.name", "Other"], other)
            path = os.path.join(other, "src", "server", "communities", "karaoke.ts")
            with open(path) as f:
                text = f.read()
            with open(path, "w") as f:
                f.write(text.replace("ingestion: 'manual'", "ingestion: 'faurax'"))
            _run(["commit", "-am", "someone else's change"], other)
            _run(["push", "origin", "main"], other)

            result = salsa_social_edit.edit_community(
                "karaoke", {"status": "live"}, {"status": "hidden", "ingestion": "manual"},
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "edit.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("reload", result["message"])
            self.assertIn("ingestion", result["message"])


class CreateCommunityTests(unittest.TestCase):
    def test_successful_create_commits_and_pushes(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            result = salsa_social_edit.create_community(
                "my-city", "My City socials", "https://my-city.pages.dev", ["my-city.pages.dev"],
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "create.log"),
            )
            self.assertTrue(result["ok"], result.get("message"))
            self.assertTrue(result["commit"])
            self.assertEqual(result["id"], 3)

            ts_path = os.path.join(clone, "src", "server", "communities", "my-city.ts")
            with open(ts_path) as f:
                ts_text = f.read()
            self.assertIn("id: 3", ts_text)
            self.assertIn("slug: 'my-city'", ts_text)
            self.assertIn("status: 'hidden'", ts_text)
            self.assertIn("ingestion: 'manual'", ts_text)
            self.assertIn("attendanceTaps: false", ts_text)

            with open(os.path.join(clone, "src", "server", "communities", "index.ts")) as f:
                index_text = f.read()
            self.assertIn("import { my_city } from './my-city.ts';", index_text)
            self.assertIn("[karaoke, my_city]", index_text)

            checklist_path = os.path.join(clone, "docs", "launch-checklists", "my-city.md")
            with open(checklist_path) as f:
                checklist_text = f.read()
            self.assertIn("- [x] Every page sends `noindex, nofollow`", checklist_text)
            self.assertIn("- [ ] Titles and meta descriptions on every page", checklist_text)

            log = _run(["log", "--oneline", "-1"], origin)
            self.assertIn("create my-city", log)

    def test_refused_bad_slug_touches_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            before = _run(["rev-parse", "main"], origin)
            result = salsa_social_edit.create_community(
                "My City", "My City socials", "https://my-city.pages.dev", ["my-city.pages.dev"],
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "create.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("slug", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], origin))
            self.assertFalse(os.path.exists(os.path.join(clone, "src", "server", "communities", "My City.ts")))

    def test_refused_slug_already_used(self):
        with tempfile.TemporaryDirectory() as root:
            clone, _origin = make_repo(root)
            result = salsa_social_edit.create_community(
                "karaoke", "Another karaoke", "https://other.pages.dev", ["other.pages.dev"],
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "create.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("already exists", result["message"])

    def test_refused_host_already_used(self):
        with tempfile.TemporaryDirectory() as root:
            clone, _origin = make_repo(root)
            result = salsa_social_edit.create_community(
                "my-city", "My City socials", "https://my-city.pages.dev", ["karaokeparis.pages.dev"],
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "create.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("karaokeparis.pages.dev", result["message"])

    def test_refused_bad_origin(self):
        with tempfile.TemporaryDirectory() as root:
            clone, _origin = make_repo(root)
            result = salsa_social_edit.create_community(
                "my-city", "My City socials", "http://my-city.pages.dev", ["my-city.pages.dev"],
                salsa_dir=clone, run_checks=ok_checks,
                log_path=os.path.join(root, "create.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("origin", result["message"])

    def test_refused_failing_check_undoes_all_new_and_changed_files(self):
        with tempfile.TemporaryDirectory() as root:
            clone, origin = make_repo(root)
            before = _run(["rev-parse", "main"], origin)
            with open(os.path.join(clone, "src", "server", "communities", "index.ts")) as f:
                original_index = f.read()

            result = salsa_social_edit.create_community(
                "my-city", "My City socials", "https://my-city.pages.dev", ["my-city.pages.dev"],
                salsa_dir=clone, run_checks=failing_checks("npm test", "1 test failed"),
                log_path=os.path.join(root, "create.log"),
            )
            self.assertFalse(result["ok"])
            self.assertIn("npm test", result["message"])
            self.assertEqual(before, _run(["rev-parse", "main"], origin))
            self.assertFalse(os.path.exists(os.path.join(clone, "src", "server", "communities", "my-city.ts")))
            self.assertFalse(os.path.exists(os.path.join(clone, "docs", "launch-checklists", "my-city.md")))
            with open(os.path.join(clone, "src", "server", "communities", "index.ts")) as f:
                self.assertEqual(original_index, f.read())


if __name__ == "__main__":
    unittest.main()
