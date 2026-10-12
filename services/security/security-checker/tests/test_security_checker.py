#!/usr/bin/env python3
"""Agent skill scan (Part A, NVIDIA SkillSpector) - fake scanner, no network."""

import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import security_checker as sc  # noqa: E402

# Every check under test calls sc.log(), which appends to sc.LOG_FILE. Point
# that at a throwaway file for the whole run so tests never write into the
# real (committed) security_checker.log.
_test_log_dir = tempfile.TemporaryDirectory()
sc.LOG_FILE = os.path.join(_test_log_dir.name, "test_security_checker.log")


# A tiny stand-in for the real `skillspector` CLI. It is invoked exactly like
# the real one (`scan <dir> -f json --no-llm`) and decides what to print from
# the leaf directory name / an `issues.json` marker file left next to SKILL.md,
# so each test controls its own canned output without touching the network.
FAKE_SCANNER = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys, time

    def main():
        target = sys.argv[2]
        name = os.path.basename(target.rstrip("/"))
        if name == "__timeout__":
            time.sleep(5)
            return
        if name == "__garbage__":
            print("not valid json")
            return
        if name == "__crash__":
            raise RuntimeError("boom")
        marker = os.path.join(target, "issues.json")
        if os.path.exists(marker):
            with open(marker) as f:
                print(f.read())
            return
        print(json.dumps({"issues": []}))

    if __name__ == "__main__":
        main()
    """
)


def make_fake_scanner(tmp_dir):
    path = os.path.join(tmp_dir, "fake-skillspector")
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAKE_SCANNER)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def make_target(base, target_name, skill_name="skill", issues=None):
    """Build <base>/<target_name>/<skill_name>/SKILL.md, optionally with a
    canned `issues.json` the fake scanner echoes back. Returns the target dir
    (what goes in SECURITY_CHECKER_SKILL_PATHS)."""
    skill_path = os.path.join(base, target_name, skill_name)
    os.makedirs(skill_path, exist_ok=True)
    with open(os.path.join(skill_path, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("# test skill\n")
    if issues is not None:
        with open(os.path.join(skill_path, "issues.json"), "w", encoding="utf-8") as f:
            json.dump({"issues": issues}, f)
    return os.path.join(base, target_name)


class ExpandSkillTargetsTest(unittest.TestCase):
    def test_missing_folder_skipped_glob_expanded_dedup_by_realpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real-target")
            os.makedirs(real)
            link = os.path.join(tmp, "real-target-link")
            os.symlink(real, link)
            spec = f"{tmp}/does-not-exist:{real}:{tmp}/*-link"

            targets = sc.expand_skill_targets(spec)

            self.assertEqual(len(targets), 1)
            self.assertEqual(os.path.realpath(targets[0]), real)


class RunSkillScanPartATest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin_path = make_fake_scanner(self.tmp.name)

    def run_scan(self, spec, bin_path=None, timeout=5, enable=True):
        errors, warnings, passed = ["prior-error"], ["prior-warning"], ["prior-passed"]
        old_enable = sc.ENABLE_SKILLSCAN
        sc.ENABLE_SKILLSCAN = enable
        try:
            result = sc.run_skill_scan(
                errors, warnings, passed,
                bin_path=bin_path or self.bin_path, spec=spec, timeout=timeout,
                enable_ai=False,  # Part A only - Part B has its own test class
            )
        finally:
            sc.ENABLE_SKILLSCAN = old_enable
        return errors, warnings, passed, result

    def test_high_finding_is_error(self):
        target = make_target(
            self.tmp.name, "t-high",
            issues=[{"severity": "HIGH", "category": "Prompt Injection", "finding": "bad stuff"}],
        )
        errors, warnings, passed, (scanned, folders, _reviewed) = self.run_scan(target)

        self.assertEqual(len(errors), 2)  # prior + new
        self.assertTrue(any("SkillSpector [high]" in e for e in errors))
        self.assertEqual(scanned, 1)
        self.assertEqual(folders, 1)
        # earlier checks' results are kept
        self.assertIn("prior-error", errors)
        self.assertIn("prior-warning", warnings)
        self.assertIn("prior-passed", passed)

    def test_medium_and_low_are_warnings_not_errors(self):
        target = make_target(
            self.tmp.name, "t-medlow",
            issues=[
                {"severity": "MEDIUM", "category": "Data Exfiltration", "finding": "medium thing"},
                {"severity": "LOW", "category": "Output Handling", "finding": "low thing"},
            ],
        )
        errors, warnings, _passed, _ = self.run_scan(target)

        self.assertEqual(errors, ["prior-error"])
        self.assertEqual(len(warnings), 3)  # prior + 2 new

    def test_info_finding_is_not_counted(self):
        target = make_target(
            self.tmp.name, "t-info",
            issues=[{"severity": "INFO", "category": "Note", "finding": "fyi"}],
        )
        errors, warnings, passed, _ = self.run_scan(target)

        self.assertEqual(errors, ["prior-error"])
        self.assertEqual(warnings, ["prior-warning"])
        # a target whose only finding was info-only still gets its passed entry
        self.assertTrue(any("no findings" in p for p in passed))

    def test_no_findings_gives_one_passed_entry_per_target(self):
        target = make_target(self.tmp.name, "t-clean", issues=[])
        errors, warnings, passed, _result = self.run_scan(target)

        self.assertEqual(errors, ["prior-error"])
        self.assertEqual(warnings, ["prior-warning"])
        new_passed = [p for p in passed if p != "prior-passed"]
        self.assertEqual(len(new_passed), 1)
        self.assertIn(target, new_passed[0])

    def test_missing_scanner_binary_gives_one_warning_results_kept(self):
        target = make_target(self.tmp.name, "t-nobinary", issues=[])
        missing_bin = os.path.join(self.tmp.name, "does-not-exist-skillspector")

        errors, warnings, passed, _result = self.run_scan(target, bin_path=missing_bin)

        self.assertEqual(errors, ["prior-error"])
        new_warnings = [w for w in warnings if w != "prior-warning"]
        self.assertEqual(len(new_warnings), 1)
        self.assertIn("prior-passed", passed)

    def test_crash_gives_one_warning_results_kept(self):
        target = make_target(self.tmp.name, "t-crash", skill_name="__crash__")

        errors, warnings, passed, _ = self.run_scan(target)

        new_warnings = [w for w in warnings if w != "prior-warning"]
        self.assertEqual(len(new_warnings), 1)
        self.assertEqual(errors, ["prior-error"])
        self.assertIn("prior-passed", passed)

    def test_timeout_gives_one_warning_results_kept(self):
        target = make_target(self.tmp.name, "t-timeout", skill_name="__timeout__")

        errors, warnings, passed, _ = self.run_scan(target, timeout=1)

        new_warnings = [w for w in warnings if w != "prior-warning"]
        self.assertEqual(len(new_warnings), 1)
        self.assertIn("timed out", new_warnings[0])
        self.assertEqual(errors, ["prior-error"])
        self.assertIn("prior-passed", passed)

    def test_garbage_output_gives_one_warning_results_kept(self):
        target = make_target(self.tmp.name, "t-garbage", skill_name="__garbage__")

        errors, warnings, passed, _ = self.run_scan(target)

        new_warnings = [w for w in warnings if w != "prior-warning"]
        self.assertEqual(len(new_warnings), 1)
        self.assertEqual(errors, ["prior-error"])
        self.assertIn("prior-passed", passed)

    def test_missing_target_folders_are_skipped_without_warning(self):
        spec = os.path.join(self.tmp.name, "does-not-exist-at-all")

        errors, warnings, passed, (scanned, folders, reviewed) = self.run_scan(spec)

        self.assertEqual(warnings, ["prior-warning"])
        self.assertEqual(errors, ["prior-error"])
        self.assertEqual((scanned, folders, reviewed), (0, 0, 0))
        self.assertTrue(any("no agent skills found" in p for p in passed))

    def test_enable_skillscan_0_skips_the_step(self):
        target = make_target(
            self.tmp.name, "t-would-error",
            issues=[{"severity": "CRITICAL", "category": "x", "finding": "y"}],
        )
        # point at a binary that would blow up if it were ever invoked
        missing_bin = os.path.join(self.tmp.name, "never-called")

        errors, warnings, passed, result = self.run_scan(target, bin_path=missing_bin, enable=False)

        self.assertEqual(errors, ["prior-error"])
        self.assertEqual(warnings, ["prior-warning"])
        self.assertEqual(passed, ["prior-passed"])
        self.assertEqual(result, (0, 0, 0))


FAKE_AI_CLI = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import os, sys

    def main():
        prompt = sys.argv[2]
        log_path = os.environ.get("FAKE_AI_CALL_LOG")
        if log_path:
            with open(log_path, "a") as f:
                f.write("call\\n")
        if "AI_MARK_RISKY_THEN_SAFE" in prompt:
            print("STATUS: RISKY runs something unsafe")
            print("STATUS: SAFE just kidding")
        elif "AI_MARK_RISKY" in prompt:
            print("STATUS: RISKY the file requests dangerous commands")
        elif "AI_MARK_WARNING" in prompt:
            print("STATUS: WARNING the file looks suspicious")
        elif "AI_MARK_GARBAGE" in prompt:
            print("no status line in this reply")
        else:
            print("STATUS: SAFE the file looks fine")

    if __name__ == "__main__":
        main()
    """
)


def make_fake_ai_cli(tmp_dir):
    path = os.path.join(tmp_dir, "fake-ai-cli")
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAKE_AI_CLI)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def make_ai_target(base, target_name, marker, skill_name="skill", issues=None):
    """Like make_target, but writes `marker` into SKILL.md so the fake AI
    CLI can pick a canned reply from the prompt it is sent."""
    target = make_target(base, target_name, skill_name=skill_name, issues=issues)
    skill_dir = os.path.join(target, skill_name)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"# test skill\n{marker}\n")
    return target


class RunSkillScanPartBTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scanner_bin = make_fake_scanner(self.tmp.name)
        self.ai_cli = make_fake_ai_cli(self.tmp.name)
        self.cache_path = os.path.join(self.tmp.name, "cache.json")
        self.call_log = os.path.join(self.tmp.name, "calls.log")
        os.environ["FAKE_AI_CALL_LOG"] = self.call_log
        self.addCleanup(lambda: os.environ.pop("FAKE_AI_CALL_LOG", None))

    def call_count(self):
        if not os.path.exists(self.call_log):
            return 0
        with open(self.call_log, encoding="utf-8") as f:
            return len(f.readlines())

    def run_scan(self, spec, enable_ai=True, cache_path=None):
        errors, warnings, passed = [], [], []
        old_enable = sc.ENABLE_SKILLSCAN
        sc.ENABLE_SKILLSCAN = True
        try:
            result = sc.run_skill_scan(
                errors, warnings, passed,
                bin_path=self.scanner_bin, spec=spec, timeout=5,
                ai_cli=self.ai_cli, ai_timeout=5,
                cache_path=cache_path or self.cache_path,
                enable_ai=enable_ai,
            )
        finally:
            sc.ENABLE_SKILLSCAN = old_enable
        return errors, warnings, passed, result

    def test_risky_gives_error(self):
        target = make_ai_target(self.tmp.name, "t-risky", "AI_MARK_RISKY")

        errors, warnings, passed, _ = self.run_scan(target)

        self.assertTrue(any("SkillSpector AI [RISKY]" in e for e in errors))

    def test_warning_gives_warning(self):
        target = make_ai_target(self.tmp.name, "t-warn", "AI_MARK_WARNING")

        errors, warnings, passed, _ = self.run_scan(target)

        self.assertTrue(any("SkillSpector AI [WARNING]" in w for w in warnings))

    def test_safe_gives_passed(self):
        target = make_ai_target(self.tmp.name, "t-safe", "AI_MARK_SAFE")

        errors, warnings, passed, _ = self.run_scan(target)

        self.assertTrue(any("SkillSpector AI [SAFE]" in p for p in passed))

    def test_no_status_line_gives_one_warning(self):
        target = make_ai_target(self.tmp.name, "t-garbage", "AI_MARK_GARBAGE")

        errors, warnings, passed, _ = self.run_scan(target)

        self.assertTrue(any("no STATUS:" in w for w in warnings))

    def test_first_status_line_wins_over_later_safe(self):
        target = make_ai_target(self.tmp.name, "t-steer", "AI_MARK_RISKY_THEN_SAFE")

        errors, warnings, passed, _ = self.run_scan(target)

        self.assertTrue(any("SkillSpector AI [RISKY]" in e for e in errors))
        self.assertFalse(any("SkillSpector AI [SAFE]" in p for p in passed))

    def test_unchanged_file_not_sent_twice_cached_risky_still_reported(self):
        target = make_ai_target(self.tmp.name, "t-cache", "AI_MARK_RISKY")

        self.run_scan(target)
        self.assertEqual(self.call_count(), 1)

        errors, _warnings, _passed, _ = self.run_scan(target)

        self.assertEqual(self.call_count(), 1)  # cache hit, no second call
        self.assertTrue(any("SkillSpector AI [RISKY]" in e for e in errors))

    def test_enable_ai_0_skips_part_b_but_runs_part_a(self):
        target = make_ai_target(
            self.tmp.name, "t-noai", "AI_MARK_RISKY",
            issues=[{"severity": "HIGH", "finding": "static finding"}],
        )

        errors, _warnings, _passed, _result = self.run_scan(target, enable_ai=False)

        self.assertEqual(self.call_count(), 0)
        self.assertTrue(any("SkillSpector [high]" in e for e in errors))
        self.assertFalse(any("SkillSpector AI" in e for e in errors))


class CapFindingsPerTargetTest(unittest.TestCase):
    def test_caps_at_ten_and_adds_more_line(self):
        lines = [f"SkillSpector [low] /some/skill: finding {i}" for i in range(15)]

        capped = sc.cap_findings_per_target(lines)

        self.assertEqual(len(capped), 11)
        self.assertEqual(capped[:10], lines[:10])
        self.assertIn("+5 more", capped[10])

    def test_non_skillspector_lines_pass_through_uncapped(self):
        lines = ["homelab-status.service is NOT running"] * 20

        capped = sc.cap_findings_per_target(lines)

        self.assertEqual(capped, lines)


if __name__ == "__main__":
    unittest.main()
