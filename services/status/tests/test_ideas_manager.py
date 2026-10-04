#!/usr/bin/env python3
"""The Obsidian-backed ideas board: parsing, editing, labels and challenges.

Every test runs against a throwaway vault in a temp dir, with the Obsidian
sync hook stubbed out so nothing is dispatched to the real app.
"""

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ideas_manager  # noqa: E402
from ideas_manager import (  # noqa: E402
    add_idea,
    answer_challenge,
    append_note,
    challenge_rejection,
    discover_backend_files,
    extract_labels,
    find_ideas,
    list_all_ideas,
    parse_active_file,
    split_title_and_inline_notes,
    update_idea,
)

MONEY = "Money making.md"
FOSS = "FOSS projects.md"
FRONTMATTER = "---\ntags:\n  - myJira/backend\n  - board\n---\n"


class VaultTestCase(unittest.TestCase):
    """A temp vault wired in through PROJECT_IDEAS_DIR."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._env = os.environ.get("PROJECT_IDEAS_DIR")
        os.environ["PROJECT_IDEAS_DIR"] = self.dir
        self._sync = ideas_manager.trigger_obsidian_sync
        ideas_manager.trigger_obsidian_sync = lambda reason="": None

    def tearDown(self):
        ideas_manager.trigger_obsidian_sync = self._sync
        if self._env is None:
            os.environ.pop("PROJECT_IDEAS_DIR", None)
        else:
            os.environ["PROJECT_IDEAS_DIR"] = self._env
        shutil.rmtree(self.dir)

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(content))

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return f.read()

    def idea(self, title, **filters):
        for i in list_all_ideas(**filters):
            if i["title"] == title:
                return i
        self.fail(f"no idea titled {title!r}")


class TitleParsingTests(unittest.TestCase):
    def test_split_title_and_inline_notes(self):
        line = "- [ ] Thread meeting-room screen (cheap) — [SHELVED ON CAPITAL] BOO-199: curves DO cross at n~100"
        title, notes = split_title_and_inline_notes(line)
        self.assertEqual(title, "Thread meeting-room screen (cheap)")
        self.assertEqual(notes, "[SHELVED ON CAPITAL] BOO-199: curves DO cross at n~100")

    def test_split_title_bold_and_dashes(self):
        line = "- [ ] **PEA automation (FR only)** — surviving finding from BOO-222, deliberately untagged."
        title, notes = split_title_and_inline_notes(line)
        self.assertEqual(title, "PEA automation (FR only)")
        self.assertTrue(notes.startswith("surviving finding"))

    def test_tags_never_leak_into_the_title(self):
        title, _ = split_title_and_inline_notes("- [ ] `[ONGOING]` FARAH ERP #status/ongoing #owned #erp")
        self.assertEqual(title, "FARAH ERP")

    def test_labels_exclude_state_tags_and_non_tags(self):
        text = "Farah #status/next #owned #SaaS #myJira/backend ranks #1 in C# #owned"
        self.assertEqual(extract_labels(text), ["owned", "saas"])


class BackendDiscoveryTests(VaultTestCase):
    def test_frontmatter_block_list(self):
        self.write("a.md", FRONTMATTER + "- [ ] x\n")
        self.write("b.md", "- [ ] not a board\n")
        self.assertEqual(discover_backend_files(self.dir), ["a.md"])

    def test_frontmatter_key_inline_list_and_body_tag(self):
        self.write("key.md", "---\nmyJira: backend\n---\n")
        self.write("inline.md", "---\ntags: [board, myJira/backend]\n---\n")
        self.write("body.md", "# Board\n#myJira/backend\n- [ ] y\n")
        self.write("quoted.md", "mentions `#myJira/backend` in code only\n")
        self.assertEqual(discover_backend_files(self.dir), ["body.md", "inline.md", "key.md"])

    def test_ceo_notes_are_never_a_backend(self):
        self.write("Idea Feasibility Agent.md", FRONTMATTER)
        self.write(MONEY, FRONTMATTER)
        self.assertEqual(discover_backend_files(self.dir), [MONEY])

    def test_falls_back_to_defaults_when_nothing_is_tagged(self):
        self.write(MONEY, "- [ ] a\n")
        self.write(FOSS, "- [ ] b\n")
        self.write("other.md", "- [ ] c\n")
        self.assertEqual(discover_backend_files(self.dir), [MONEY, FOSS])

    def test_board_lists_only_backends(self):
        self.write("4 - Side bets.md", FRONTMATTER + "## Misc\n- [ ] New board idea\n")
        self.write("Money making - analyzed.md", "## Old\n- [ ] Stale analysis\n")
        titles = [i["title"] for i in list_all_ideas()]
        self.assertEqual(titles, ["New board idea"])
        self.assertEqual(list(ideas_manager.get_categories()), ["4 - Side bets.md"])


class ProjectBoardTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.write(MONEY, FRONTMATTER + "## Active\n- [ ] `[ONGOING]` FARAH ERP #status/ongoing #owned\n")

    def test_create_board_is_discovered_and_linked_from_its_ticket(self):
        res = ideas_manager.create_board("FARAH ERP", sections=["Features", "Bugs"], parent=MONEY)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["file"], "PROJECTS/FARAH ERP.md")
        self.assertEqual(discover_backend_files(self.dir), [MONEY, "PROJECTS/FARAH ERP.md"])
        self.assertEqual(ideas_manager.get_categories()["PROJECTS/FARAH ERP.md"], ["Features", "Bugs"])
        self.assertIn("[[Money making]]", self.read("PROJECTS/FARAH ERP.md"))
        self.assertEqual(self.idea("FARAH ERP")["board"], "PROJECTS/FARAH ERP.md")

        again = ideas_manager.create_board("FARAH ERP")
        self.assertFalse(again["ok"])
        self.assertTrue(again["exists"])

    def test_cards_can_be_added_to_and_moved_on_a_project_board(self):
        ideas_manager.create_board("FARAH ERP", sections=["Features"])
        res = add_idea("Low-stock alerts", category="Features", target_file="PROJECTS/FARAH ERP.md", status="next")
        self.assertTrue(res["ok"], res)
        task = self.idea("Low-stock alerts", file_filter="PROJECTS/FARAH ERP.md")
        self.assertEqual((task["category"], task["status"], task["board"]), ("Features", "next", None))
        res = ideas_manager.update_idea_status(task["id"], "ongoing")
        self.assertTrue(res["ok"], res)
        self.assertIn("## Features\n\n- [ ] Low-stock alerts #status/ongoing", self.read("PROJECTS/FARAH ERP.md"))

    def test_existing_note_is_adopted_not_overwritten(self):
        self.write("PROJECTS/Cockpit.md", "# TODOs\n\n- Slack bot\n")
        res = ideas_manager.create_board("Cockpit")
        self.assertTrue(res["adopted"], res)
        content = self.read("PROJECTS/Cockpit.md")
        self.assertTrue(content.startswith("---\ntags:\n  - myJira/backend"))
        self.assertIn("# TODOs\n\n- Slack bot\n", content)
        self.assertEqual([i["title"] for i in list_all_ideas(file_filter="PROJECTS/Cockpit.md")], ["Slack bot"])

    def test_adopt_keeps_other_frontmatter_tags(self):
        self.write("PROJECTS/A.md", "---\ntags: [work]\nstatus: x\n---\nbody\n")
        self.write("PROJECTS/B.md", "---\ntags:\n  - work\n---\nbody\n")
        ideas_manager.create_board("A")
        ideas_manager.create_board("B")
        self.assertIn("tags: [work, myJira/backend]\nstatus: x", self.read("PROJECTS/A.md"))
        self.assertIn("tags:\n  - myJira/backend\n  - work\n", self.read("PROJECTS/B.md"))
        self.assertEqual(discover_backend_files(self.dir), [MONEY, "PROJECTS/A.md", "PROJECTS/B.md"])

    def test_names_and_paths_cannot_escape_the_vault(self):
        res = ideas_manager.create_board("../../etc/passwd")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["file"], "PROJECTS/etc passwd.md")
        self.assertFalse(ideas_manager.create_board("  #  ")["ok"])
        self.assertFalse(add_idea("x", target_file="../outside.md")["ok"])
        self.assertFalse(add_idea("x", target_file="rejected/rejected.md")["ok"])

    def test_rejected_folder_is_never_a_board(self):
        self.write("rejected/rejected.md", FRONTMATTER + "### Dossier\n")
        self.assertEqual(discover_backend_files(self.dir), [MONEY])


class CalloutTests(VaultTestCase):
    BLOCK = FRONTMATTER + textwrap.dedent("""\
        ## Web
        - [ ] BRS Simulator #web — French housing calculator
          > [!info]- Deep Analysis & Viability (Rank 2)
          > * **Category:** Web Application
          >   * nested point
          >
          > * **Next Action:** code the formulas
        - [ ] Other idea
        """)

    def test_callout_is_child_content_of_its_ticket(self):
        self.write(MONEY, self.BLOCK)
        brs = self.idea("BRS Simulator")
        self.assertEqual(brs["tags"], ["web"])
        self.assertEqual(brs["notes"].split("\n")[0], "French housing calculator")
        self.assertIn("> [!info]- Deep Analysis & Viability (Rank 2)", brs["notes"])
        self.assertIn(">   * nested point", brs["notes"])
        self.assertEqual(self.idea("Other idea")["notes"], "")

    def test_edit_round_trips_the_callout(self):
        self.write(MONEY, self.BLOCK)
        brs = self.idea("BRS Simulator")
        res = update_idea(brs["id"], title="BRS & PTZ Simulator", notes=brs["notes"])
        self.assertTrue(res["ok"], res)
        after = self.read(MONEY)
        self.assertIn("- [ ] BRS & PTZ Simulator #web — French housing calculator\n"
                      "  > [!info]- Deep Analysis & Viability (Rank 2)\n", after)
        self.assertIn("  >   * nested point\n  >\n", after)
        self.assertTrue(after.startswith(FRONTMATTER))


class LabelEditTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.write(MONEY, FRONTMATTER + "## Hardware\n- [ ] My Quick Title\n")

    def test_update_title_and_notes(self):
        idea = self.idea("My Quick Title")
        res = update_idea(idea["id"], title="Polished Title", notes="Detailed rationale here")
        self.assertTrue(res["ok"])
        self.assertIn("- [ ] Polished Title — Detailed rationale here", self.read(MONEY))

    def test_tags_are_set_independently_of_status(self):
        idea = self.idea("My Quick Title")
        update_idea(idea["id"], status="next")
        idea = self.idea("My Quick Title")
        update_idea(idea["id"], tags=["owned", "#Hardware"])
        idea = self.idea("My Quick Title")
        self.assertEqual(idea["status"], "next")
        self.assertEqual(idea["tags"], ["owned", "hardware"])
        self.assertIn("- [ ] My Quick Title #status/next #owned #hardware", self.read(MONEY))

        update_idea(idea["id"], tags="hardware")
        idea = self.idea("My Quick Title")
        self.assertEqual(idea["tags"], ["hardware"])
        self.assertEqual(idea["status"], "next")

    def test_owned_survives_title_edits_and_status_moves(self):
        idea = self.idea("My Quick Title")
        update_idea(idea["id"], tags=["owned"])
        idea = self.idea("My Quick Title")
        update_idea(idea["id"], title="Farah ERP")
        idea = self.idea("Farah ERP")
        ideas_manager.update_idea_status(idea["id"], "ongoing")
        idea = self.idea("Farah ERP")
        self.assertEqual(idea["status"], "ongoing")
        self.assertEqual(idea["tags"], ["owned"])

    def test_labels_typed_in_the_title_become_labels(self):
        idea = self.idea("My Quick Title")
        update_idea(idea["id"], title="Farah ERP #owned")
        idea = self.idea("Farah ERP")
        self.assertEqual(idea["tags"], ["owned"])

    def test_add_idea_with_tags(self):
        res = add_idea("Farah ERP", category="Hardware", target_file=MONEY, tags=["owned", "erp"])
        self.assertTrue(res["ok"])
        self.assertEqual(res["tags"], ["owned", "erp"])
        self.assertEqual(self.idea("Farah ERP")["tags"], ["owned", "erp"])

    def test_new_category_lands_after_the_frontmatter(self):
        add_idea("Brand new", category="Fresh Section", target_file=MONEY)
        content = self.read(MONEY)
        self.assertTrue(content.startswith(FRONTMATTER), content)
        self.assertIn("## Fresh Section\n\n- [ ] Brand new", content)


class ChallengeVault(VaultTestCase):
    """A board with one rejected bullet."""

    def setUp(self):
        super().setUp()
        self.write(MONEY, FRONTMATTER + textwrap.dedent("""\
            ## Hardware
            - [ ] Live idea #status/next
            - [ ] Smart Scanner #status/rejected #hardware — Margin below 15 EUR/unit
              - BOM analysis attached
            """))


class ChallengeTests(ChallengeVault):

    def test_only_rejected_ideas_can_be_challenged(self):
        res = challenge_rejection(self.idea("Live idea")["id"], "why not")
        self.assertFalse(res["ok"])
        res = challenge_rejection(self.idea("Smart Scanner")["id"], "  ")
        self.assertFalse(res["ok"])

    def test_challenge_active_bullet(self):
        scanner = self.idea("Smart Scanner")
        self.assertEqual(scanner["rejection_reason"], "Margin below 15 EUR/unit")
        res = challenge_rejection(scanner["id"], "Off-the-shelf shells: margin is 45%.\nSee the BoM.")
        self.assertTrue(res["ok"], res)

        content = self.read(MONEY)
        today = ideas_manager._today()
        self.assertIn(
            "- [ ] Smart Scanner #status/rejected #hardware #rejection_challenged — Margin below 15 EUR/unit\n"
            "  - BOM analysis attached\n"
            f"  - **Challenge ({today})**: Off-the-shelf shells: margin is 45%.\n"
            "    See the BoM.", content)
        scanner = self.idea("Smart Scanner")
        self.assertEqual(scanner["id"], res["id"])
        self.assertEqual(scanner["status"], "rejected")
        self.assertEqual(scanner["tags"], ["hardware", "rejection_challenged"])

    def test_answer_upheld_keeps_it_rejected(self):
        scanner = self.idea("Smart Scanner")
        res = challenge_rejection(scanner["id"], "margin is fine")
        res = answer_challenge(res["id"], "Shipping kills it anyway.", "upheld")
        self.assertTrue(res["ok"], res)
        scanner = self.idea("Smart Scanner")
        self.assertEqual(scanner["status"], "rejected")
        self.assertEqual(scanner["tags"], ["hardware", "rejection_answered"])
        self.assertIn("**Feasibility Answer (", scanner["notes"])
        self.assertIn("[upheld] Shipping kills it anyway.", scanner["notes"])

    def test_answer_accepted_moves_it_to_next(self):
        scanner = self.idea("Smart Scanner")
        res = challenge_rejection(scanner["id"], "margin is fine")
        res = answer_challenge(res["id"], "BoM validated.", "accepted")
        self.assertTrue(res["ok"], res)
        scanner = self.idea("Smart Scanner")
        self.assertEqual(scanner["status"], "next")
        self.assertEqual(scanner["tags"], ["hardware", "rejection_answered"])
        self.assertNotIn("#status/rejected", self.read(MONEY))
        # Only the two verdicts the Idea Feasibility Agent instructions name are accepted.
        res = answer_challenge(scanner["id"], "x", "maybe")
        self.assertFalse(res["ok"])

    def test_rechallenge_drops_the_answered_tag(self):
        scanner = self.idea("Smart Scanner")
        res = challenge_rejection(scanner["id"], "first")
        res = answer_challenge(res["id"], "no", "upheld")
        res = challenge_rejection(res["id"], "second")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.idea("Smart Scanner")["tags"], ["hardware", "rejection_challenged"])

class CliTests(ChallengeVault):
    def test_ceo_lists_and_answers_challenges(self):
        import contextlib
        import io
        import json

        challenge_rejection(self.idea("Smart Scanner")["id"], "margin is 45%")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ideas_manager._cli(["challenged"]), 0)
        pending = json.loads(out.getvalue())
        self.assertEqual([p["title"] for p in pending], ["Smart Scanner"])
        self.assertEqual(pending[0]["challenge"], "margin is 45%")
        self.assertEqual(pending[0]["rejection_reason"], "Margin below 15 EUR/unit")

        with contextlib.redirect_stdout(io.StringIO()):
            code = ideas_manager._cli(["answer", pending[0]["id"], "upheld", "Shipping still kills it."])
        self.assertEqual(code, 0)
        self.assertEqual(self.idea("Smart Scanner")["tags"], ["hardware", "rejection_answered"])


class AppendNoteTests(VaultTestCase):
    def test_append_and_find(self):
        self.write(MONEY, FRONTMATTER + "## A\n- [ ] Farah ERP #owned\n  - existing\n- [ ] Farah Cafe\n")
        hits = find_ideas("farah erp")
        self.assertEqual(hits[0]["title"], "Farah ERP")
        self.assertEqual(find_ideas("zzz"), [])
        res = append_note(hits[0]["id"], "Add stock alerts", source="Slack")
        self.assertTrue(res["ok"], res)
        self.assertIn("  - existing\n  - **Note via Slack (", self.read(MONEY))
        self.assertIn("Add stock alerts\n- [ ] Farah Cafe", self.read(MONEY))


class StatusTagTests(VaultTestCase):
    def test_every_status_is_a_status_tag(self):
        self.write(MONEY, FRONTMATTER + textwrap.dedent("""\
            ## Active
            - [ ] Plain
            - [ ] Soon #status/next #saas
            - [ ] Busy #status/ongoing
            - [ ] Costly #status/shelved — needs capital
            - [ ] Dead #status/rejected — rejected because #status/next is wrong here
            """))
        got = {i["title"]: (i["status"], i["tags"]) for i in parse_active_file(self.dir, MONEY)}
        self.assertEqual(got, {
            "Plain": ("untagged", []),
            "Soon": ("next", ["saas"]),
            "Busy": ("ongoing", []),
            "Costly": ("shelved", []),
            "Dead": ("rejected", []),
        })

    def test_status_change_rewrites_legacy_markers_as_one_tag(self):
        self.write(MONEY, FRONTMATTER + "## Active\n- [ ] `[ONGOING]` Old card #board/ongoing #owned — note\n")
        card = self.idea("Old card")
        self.assertEqual(card["status"], "ongoing")
        res = ideas_manager.update_idea_status(card["id"], "next")
        self.assertTrue(res["ok"], res)
        self.assertIn("- [ ] Old card #owned #status/next — note", self.read(MONEY))

    def test_rejecting_keeps_the_card_in_place_with_its_reason(self):
        self.write(MONEY, FRONTMATTER + "## Active\n- [ ] Doomed #status/next\n")
        res = ideas_manager.update_idea_status(self.idea("Doomed")["id"], "shelved", "too costly")
        self.assertTrue(res["ok"], res)
        today = ideas_manager._today()
        self.assertIn(f"- [ ] Doomed #status/shelved\n  - **Shelved ({today})**: too costly", self.read(MONEY))
        self.assertEqual(self.idea("Doomed")["status"], "shelved")


class ArchiveTests(VaultTestCase):
    def test_archive_moves_rejected_and_shelved_cards_under_the_same_headings(self):
        self.write(MONEY, FRONTMATTER + textwrap.dedent("""\
            intro text

            ## Hardware

            - [ ] Keep me #status/next
            - [ ] Bad gadget #status/rejected #hw
              - why it failed
            - [ ] Costly gadget #status/shelved

            ## Software

            - [ ] Bad app #status/rejected
            - [ ] Keep me too
            """))
        self.write("Money making [REJECTED].md", "## Software\n\n- [ ] Older bad app #status/rejected\n")

        dry = ideas_manager.archive_cards(dry_run=True)
        self.assertEqual(len(dry["moved"]), 2)
        self.assertIn("Bad gadget", self.read(MONEY))

        ideas_manager.archive_cards()
        self.assertEqual(self.read(MONEY), FRONTMATTER + textwrap.dedent("""\
            intro text

            ## Hardware

            - [ ] Keep me #status/next

            ## Software

            - [ ] Keep me too
            """))
        self.assertEqual(self.read("Money making [REJECTED].md"), textwrap.dedent("""\
            ## Software

            - [ ] Older bad app #status/rejected
            - [ ] Bad app #status/rejected

            ## Hardware

            - [ ] Bad gadget #status/rejected #hw
              - why it failed
            """))
        self.assertEqual(self.read("Money making [SHELVED].md"),
                         "## Hardware\n\n- [ ] Costly gadget #status/shelved\n")
        # Archive notes are not boards: the cards are off the page.
        self.assertNotIn("Bad gadget", [i["title"] for i in list_all_ideas()])
        # Running it again moves nothing.
        self.assertEqual(ideas_manager.archive_cards()["moved"], [])


class RealVaultShapeTests(VaultTestCase):
    def test_legacy_markers_still_map_to_statuses(self):
        self.write(MONEY, FRONTMATTER + textwrap.dedent("""\
            ## Active
            - [ ] `[ONGOING]` Chloé Jobs Agent #board/ongoing
            - [ ] Thread Screen `[SHELVED ON CAPITAL]` — needs capital
            - [ ] Radio `[REJECTED]` — manual labour
            - [ ] PEA engine — parked until broker APIs exist; not rejected yet
            """))
        got = {i["title"]: i["status"] for i in parse_active_file(self.dir, MONEY)}
        self.assertEqual(got, {
            "Chloé Jobs Agent": "ongoing",
            "Thread Screen": "shelved",
            "Radio": "rejected",
            "PEA engine": "untagged",
        })


if __name__ == "__main__":
    unittest.main()
