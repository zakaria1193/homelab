#!/usr/bin/env python3
"""Offline tests for the Obsidian ideas -> Kandev migration plan builder.

Every test runs against a throwaway vault in a temp dir. No HTTP, no
Obsidian: build_plan()/load_sources() only read files.
"""

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_ideas_to_kandev as migrate  # noqa: E402

MONEY = migrate.MONEY_FILE
FOSS = migrate.FOSS_FILE
REJECTED = migrate.REJECTED_FILE
TODAY = "2026-10-02"


class VaultTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(content))

    def write_defaults(self, money="", foss="", rejected=""):
        self.write(MONEY, money or "- [ ] placeholder\n")
        self.write(FOSS, foss or "")
        self.write(REJECTED, rejected or "")

    def by_title(self, items, title):
        for item in items:
            if item["title"] == title:
                return item
        self.fail(f"no planned item titled {title!r} in {[i['title'] for i in items]}")


class CountsTests(VaultTestCase):
    def test_counts_per_source(self):
        self.write(
            MONEY,
            """\
            - [ ] Card One
            - [ ] Card Two
            """,
        )
        self.write(
            FOSS,
            """\
            - [ ] FOSS Card One
            """,
        )
        self.write(
            REJECTED,
            """\
            ### Dossier One

            Some body text.

            ### Dossier Two

            Some other body text.
            """,
        )
        items = migrate.build_plan(self.dir, TODAY)
        self.assertEqual(sum(1 for i in items if i["source"] == MONEY), 2)
        self.assertEqual(sum(1 for i in items if i["source"] == FOSS), 1)
        self.assertEqual(sum(1 for i in items if i["source"] == REJECTED), 2)
        self.assertEqual(len(items), 5)
        self.assertIn("2 - Money making.md: 2 cards", migrate.summary_line(items))
        self.assertIn("total 5", migrate.summary_line(items))

    def test_missing_file_exits_non_zero(self):
        self.write(MONEY, "- [ ] a\n")
        self.write(FOSS, "- [ ] b\n")
        # rejected/rejected.md intentionally missing
        with self.assertRaises(SystemExit) as ctx:
            migrate.load_sources(self.dir)
        self.assertNotEqual(ctx.exception.code, 0)


class ColumnMappingTests(VaultTestCase):
    def test_all_five_statuses(self):
        self.write(
            MONEY,
            """\
            - [ ] Untagged Card
            - [ ] `[ONGOING]` Ongoing Card #board/ongoing
            - [ ] Next Card #board/next
            - [ ] `[SHELVED ON CAPITAL]` Shelved Card
            - [ ] `[REJECTED]` Rejected Card
            """,
        )
        self.write(FOSS, "")
        self.write(
            REJECTED,
            """\
            ### Dossier Rejected

            Rejected body.

            ### Dossier Shelved

            SHELVED body.
            """,
        )
        items = migrate.build_plan(self.dir, TODAY)
        self.assertEqual(self.by_title(items, "Untagged Card")["column"], "Untagged")
        self.assertEqual(self.by_title(items, "Ongoing Card")["column"], "Ongoing")
        self.assertEqual(self.by_title(items, "Next Card")["column"], "Next")
        self.assertEqual(self.by_title(items, "Shelved Card")["column"], "Shelved")
        self.assertEqual(self.by_title(items, "Rejected Card")["column"], "Rejected")
        self.assertEqual(self.by_title(items, "Dossier Rejected")["column"], "Rejected")
        self.assertEqual(self.by_title(items, "Dossier Shelved")["column"], "Shelved")


class LabelTests(VaultTestCase):
    def test_owned_kept_state_tags_dropped_foss_added_once(self):
        self.write(
            MONEY,
            """\
            - [ ] Owned Card #board/next #owned #myJira/backend
            """,
        )
        self.write(
            FOSS,
            """\
            - [ ] FOSS Card #saas
            - [ ] FOSS Already Tagged #foss
            """,
        )
        self.write(REJECTED, "")
        items = migrate.build_plan(self.dir, TODAY)

        owned = self.by_title(items, "Owned Card")
        self.assertIn("owned", owned["labels"])
        self.assertNotIn("board/next", owned["labels"])
        self.assertNotIn("myjira/backend", owned["labels"])

        foss_card = self.by_title(items, "FOSS Card")
        self.assertEqual(foss_card["labels"].count("foss"), 1)
        self.assertIn("saas", foss_card["labels"])

        already_tagged = self.by_title(items, "FOSS Already Tagged")
        self.assertEqual(already_tagged["labels"].count("foss"), 1)


class TitleCleaningTests(VaultTestCase):
    def test_dossier_header_strips_bold_and_status_marker(self):
        self.write(MONEY, "")
        self.write(FOSS, "")
        self.write(
            REJECTED,
            """\
            ### **Association Regulatory-Secretarial Tooling (FR)** `[REJECTED 2026-09-26]`

            Body text here.
            """,
        )
        items = migrate.build_plan(self.dir, TODAY)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["title"],
            "Association Regulatory-Secretarial Tooling (FR)",
        )


class DescriptionTests(VaultTestCase):
    def test_description_keeps_raw_line_and_notes_verbatim(self):
        self.write(
            MONEY,
            """\
            - [ ] Chloé Agent — handles `backtick` notes and €/→ symbols
              > [!info]- Deep dive
              > line one
              > line two
            """,
        )
        self.write(FOSS, "")
        self.write(REJECTED, "")
        items = migrate.build_plan(self.dir, TODAY)
        item = self.by_title(items, "Chloé Agent")

        self.assertIn(
            "`- [ ] Chloé Agent — handles `backtick` notes and €/→ symbols`",
            item["description"],
        )
        self.assertIn("handles `backtick` notes and €/→ symbols", item["description"])
        self.assertIn("> [!info]- Deep dive", item["description"])
        self.assertIn("> line one", item["description"])
        self.assertIn("> line two", item["description"])

    def test_empty_notes_is_just_the_header(self):
        self.write(MONEY, "- [ ] Bare Card\n")
        self.write(FOSS, "")
        self.write(REJECTED, "")
        items = migrate.build_plan(self.dir, TODAY)
        item = self.by_title(items, "Bare Card")
        self.assertNotIn("\n\n", item["description"])
        self.assertIn("Migrated from Obsidian", item["description"])


class ExternalIdTests(VaultTestCase):
    def test_stable_and_unique(self):
        self.write(
            MONEY,
            """\
            - [ ] Card A
            - [ ] Card B
            """,
        )
        self.write(FOSS, "")
        self.write(REJECTED, "")

        items1 = migrate.build_plan(self.dir, TODAY)
        items2 = migrate.build_plan(self.dir, "2026-12-25")

        ids1 = {i["title"]: i["external_id"] for i in items1}
        ids2 = {i["title"]: i["external_id"] for i in items2}
        self.assertEqual(ids1, ids2)

        for ext_id in ids1.values():
            self.assertTrue(ext_id.startswith("obsidian-ideas:"))
        self.assertEqual(len(set(ids1.values())), len(ids1))

    def test_duplicate_external_id_aborts(self):
        # Same raw title in the same file -> same idea id -> abort.
        self.write(
            MONEY,
            """\
            - [ ] Duplicate Card
            - [ ] Duplicate Card
            """,
        )
        self.write(FOSS, "")
        self.write(REJECTED, "")
        with self.assertRaises(SystemExit) as ctx:
            migrate.build_plan(self.dir, TODAY)
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
