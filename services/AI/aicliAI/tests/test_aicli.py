"""Tests for aicli.py against the fake CLI in tests/fake_cli/. No test runs the
real `claude` or `agy` - see homelab-0013 acceptance criterion 2."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_CLI = ROOT / "tests" / "fake_cli"
AICLI = ROOT / "aicli.py"

sys.path.insert(0, str(ROOT))
import aicli  # noqa: E402

_STATE = None


def setUpModule():
    # Keep every test - in-process and `aicli.py` subprocesses alike - off the
    # real usage log and the live routes.json the cockpit edits.
    global _STATE
    _STATE = tempfile.TemporaryDirectory()
    os.environ["AICLI_USAGE_LOG"] = str(Path(_STATE.name) / "usage.jsonl")
    os.environ["AICLI_ROUTES"] = str(Path(_STATE.name) / "routes.json")


def tearDownModule():
    os.environ.pop("AICLI_USAGE_LOG", None)
    os.environ.pop("AICLI_ROUTES", None)
    _STATE.cleanup()


def make_config(tmp_dir, **overrides):
    """A config pointing at the fake CLIs, written as a real aicli.toml so
    both the in-process functions and `aicli.py` subprocess calls see it."""
    cfg = {
        "usage_timeout": 5,
        "claude": {
            "bin": str(FAKE_CLI / "fake-claude"),
            "args": [],
            "model_flag": "--model",
            "effort_flag": "--effort",
            "tiers": {"low": "claude-haiku-5-5", "default": "claude-sonnet-5", "deep": "claude-opus-5-5"},
        },
        "agy": {
            "bin": str(FAKE_CLI / "fake-agy"),
            "args": [],
            "model_flag": "--model",
            "effort_flag": "--effort",
            "tiers": {"low": "gemini-3.8-flash-low", "default": "gemini-3.8-flash-high", "deep": "gemini-3.8-flash-high"},
        },
    }
    for tool, patch in overrides.items():
        cfg[tool].update(patch)
    path = tmp_dir / "aicli.toml"
    path.write_text(_to_toml(cfg))
    return path, cfg


def _to_toml(cfg):
    # Minimal hand-rolled TOML writer - good enough for this flat shape.
    lines = [f"usage_timeout = {cfg['usage_timeout']}"]
    for tool in ("claude", "agy"):
        t = cfg[tool]
        lines.append(f"\n[{tool}]")
        lines.append(f'bin = "{t["bin"]}"')
        lines.append(f"args = {json.dumps(t['args'])}")
        lines.append(f'model_flag = "{t["model_flag"]}"')
        lines.append(f'effort_flag = "{t["effort_flag"]}"')
        if t.get("model_sets_effort"):
            lines.append("model_sets_effort = true")
        lines.append(f"\n[{tool}.tiers]")
        for tier, model in t["tiers"].items():
            lines.append(f'{tier} = "{model}"')
    return "\n".join(lines) + "\n"


def run_aicli(*args, config_path):
    env = {**os.environ, "AICLI_CONFIG": str(config_path)}
    return subprocess.run(
        [sys.executable, str(AICLI), *args], capture_output=True, text=True, env=env,
    )


class WhichTests(unittest.TestCase):
    def test_which_prints_configured_bin(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("which", "claude", config_path=config_path)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), str(FAKE_CLI / "fake-claude"))

    def test_which_falls_back_to_path_when_configured_bin_missing(self):
        with tempfile.TemporaryDirectory() as d:
            path_dir = Path(d) / "path-bin"
            path_dir.mkdir()
            (path_dir / "claude").symlink_to(FAKE_CLI / "fake-claude")
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            env = {**os.environ, "AICLI_CONFIG": str(config_path), "PATH": f"{path_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [sys.executable, str(AICLI), "which", "claude"], capture_output=True, text=True, env=env,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), str(path_dir / "claude"))

    def test_which_skips_usr_local_bin_to_avoid_wrapper_loop(self):
        # /usr/local/bin is where the tmux-wrapper symlinks live (see
        # tools/optiplex-ai-tmux.sh); resolve_bin must never return a match
        # found there, since that would exec the wrapper and loop. Swap in a
        # stand-in SKIP_DIRS entry so the test doesn't touch the real path.
        with tempfile.TemporaryDirectory() as d:
            wrapper_dir = Path(d) / "wrapper-bin"
            wrapper_dir.mkdir()
            wrapper = wrapper_dir / "claude"
            wrapper.write_text("#!/bin/sh\necho wrapper\n")
            wrapper.chmod(0o755)
            path_dir = Path(d) / "path-bin"
            path_dir.mkdir()
            (path_dir / "claude").symlink_to(FAKE_CLI / "fake-claude")
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            config = aicli.load_config(config_path)

            old_skip, old_path = aicli.SKIP_DIRS, os.environ.get("PATH", "")
            aicli.SKIP_DIRS = {str(wrapper_dir)}
            os.environ["PATH"] = f"{wrapper_dir}:{path_dir}"
            try:
                bin_path = aicli.resolve_bin(config, "claude")
            finally:
                aicli.SKIP_DIRS, os.environ["PATH"] = old_skip, old_path
        self.assertEqual(bin_path, str(path_dir / "claude"))

    def test_which_unknown_tool_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            result = subprocess.run(
                [sys.executable, str(AICLI), "which", "claude"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path), "PATH": "/nonexistent"},
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("claude CLI not found", result.stderr)

    def test_which_rejects_bad_tool_name(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("which", "bogus", config_path=config_path)
        self.assertEqual(result.returncode, 2)


class ArgvTests(unittest.TestCase):
    def test_argv_default_tier_adds_model_flag(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("argv", "--tool", "claude", "--json", config_path=config_path)
        argv = json.loads(result.stdout)
        self.assertEqual(argv, [str(FAKE_CLI / "fake-claude"), "--model", "claude-sonnet-5"])

    def test_argv_tier_and_effort(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli(
                "argv", "--tool", "agy", "--tier", "deep", "--effort", "high", "--json",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(
            argv,
            [str(FAKE_CLI / "fake-agy"), "--model", "gemini-3.8-flash-high", "--effort", "high"],
        )

    def test_argv_model_sets_effort_drops_effort(self):
        # agy refuses `--model gemini-3.8-flash-low --effort medium`, so when
        # the tier's model names the effort, aicli must not add one.
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), agy={"model_sets_effort": True})
            result = run_aicli(
                "argv", "--tool", "agy", "--tier", "low", "--effort", "medium", "--json",
                "--", "--effort=high", "-p", "hi",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(
            argv,
            [str(FAKE_CLI / "fake-agy"), "--model", "gemini-3.8-flash-low", "-p", "hi"],
        )

    def test_argv_model_sets_effort_keeps_effort_with_caller_model(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), agy={"model_sets_effort": True})
            result = run_aicli(
                "argv", "--tool", "agy", "--effort", "high", "--json",
                "--", "--model=custom",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(argv, [str(FAKE_CLI / "fake-agy"), "--effort", "high", "--model=custom"])

    def test_argv_pass_through_args_after_dashdash(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli(
                "argv", "--tool", "claude", "--json", "--", "-p", "/usage",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(argv[-2:], ["-p", "/usage"])

    def test_argv_caller_supplied_model_flag_wins(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli(
                "argv", "--tool", "claude", "--json", "--", "--model", "custom-model",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(argv, [str(FAKE_CLI / "fake-claude"), "--model", "custom-model"])
        self.assertEqual(argv.count("--model"), 1)

    def test_argv_strips_redundant_leading_tool_name(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli(
                "argv", "--tool", "claude", "--json", "--", "claude", "--session-id", "s1",
                config_path=config_path,
            )
        argv = json.loads(result.stdout)
        self.assertEqual(argv, [str(FAKE_CLI / "fake-claude"), "--model", "claude-sonnet-5", "--session-id", "s1"])

    def test_argv_non_default_shell_quoted_line(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("argv", "--tool", "claude", config_path=config_path)
        self.assertEqual(
            result.stdout.strip(),
            f"{FAKE_CLI / 'fake-claude'} --model claude-sonnet-5",
        )

    def test_argv_unknown_tier_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("argv", "--tool", "claude", "--tier", "bogus", config_path=config_path)
        self.assertEqual(result.returncode, 2)

    def test_argv_binary_not_found_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            result = subprocess.run(
                [sys.executable, str(AICLI), "argv", "--tool", "claude"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path), "PATH": "/nonexistent"},
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("claude CLI not found", result.stderr)


class RunTests(unittest.TestCase):
    def test_run_execs_the_fake_cli_with_built_argv(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli(
                "run", "--tool", "agy", "--tier", "low", "--", "-p", "hello",
                config_path=config_path,
            )
        self.assertEqual(result.returncode, 0)
        argv = json.loads(result.stdout)
        self.assertEqual(
            argv,
            [str(FAKE_CLI / "fake-agy"), "--model", "gemini-3.8-flash-low", "-p", "hello"],
        )


class UsageTests(unittest.TestCase):
    def test_usage_json_matches_old_compute_shape(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("usage", "--json", config_path=config_path)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(
            data["claude"],
            {
                "state": "ok", "detail": "",
                "bars": {
                    "five_hour": {"pct": 76, "reset": "Aug 25, 1:09am (Europe/Paris)"},
                    "weekly": {"pct": 6, "reset": "Aug 31, 6:59pm (Europe/Paris)"},
                },
            },
        )
        self.assertEqual(data["agy"]["state"], "ok")
        # Gemini is the primary group and reported for both periods here, so
        # it wins even though "Claude and GPT models" also has a weekly line.
        self.assertEqual(data["agy"]["bars"]["weekly"]["pct"], 6)
        self.assertEqual(data["agy"]["bars"]["weekly"]["group"], "Gemini Models")
        self.assertNotIn("five_hour", data["agy"]["bars"])  # "disabled" line

    def test_usage_tool_not_found_reports_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            result = subprocess.run(
                [sys.executable, str(AICLI), "usage", "--json"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path), "PATH": "/nonexistent"},
            )
        self.assertEqual(result.returncode, 0)  # usage always exits 0
        data = json.loads(result.stdout)
        self.assertEqual(data["claude"], {"state": "unknown", "detail": "claude CLI not found", "bars": {}})

    def test_usage_readable_line_without_json(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("usage", config_path=config_path)
        self.assertIn("claude: ok", result.stdout)
        self.assertIn("agy: ok", result.stdout)


class ConfigTests(unittest.TestCase):
    def test_missing_config_file_exits_2(self):
        result = subprocess.run(
            [sys.executable, str(AICLI), "which", "claude"],
            capture_output=True, text=True,
            env={**os.environ, "AICLI_CONFIG": "/nonexistent/aicli.toml"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("/nonexistent/aicli.toml", result.stderr)

    def test_invalid_config_file_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "aicli.toml"
            bad.write_text("not = valid = toml")
            result = subprocess.run(
                [sys.executable, str(AICLI), "which", "claude"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(bad)},
            )
        self.assertEqual(result.returncode, 2)


class RoutingTests(unittest.TestCase):
    def test_resolve_route_by_class(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, config = make_config(Path(d))
            tool, tier, effort, cls = aicli.resolve_route(config, workload_class="maintenance")
            self.assertEqual((tool, tier), ("agy", "low"))
            self.assertEqual(cls, "maintenance")

            tool, tier, effort, cls = aicli.resolve_route(config, workload_class="deep-spec")
            self.assertEqual((tool, tier), ("claude", "deep"))

            tool, tier, effort, cls = aicli.resolve_route(config, workload_class="standard-dev")
            self.assertEqual((tool, tier), ("claude", "default"))

    def test_resolve_route_unknown_class_raises(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, config = make_config(Path(d))
            with self.assertRaises(ValueError):
                aicli.resolve_route(config, workload_class="nonexistent-class")

    def test_resolve_route_client_override(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, config = make_config(Path(d))
            routes = {
                "classes": {"maintenance": {"tool": "agy", "tier": "low"}},
                "clients": {"custom-client": {"class": "maintenance", "tool": "claude", "tier": "deep"}},
            }
            tool, tier, _, cls = aicli.resolve_route(config, client="custom-client", routes=routes)
            self.assertEqual((tool, tier), ("claude", "deep"))
            self.assertEqual(cls, "maintenance")

    def test_argv_with_class(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("argv", "--class", "maintenance", "--json", config_path=config_path)
            self.assertEqual(result.returncode, 0)
            argv = json.loads(result.stdout)
            self.assertEqual(argv, [str(FAKE_CLI / "fake-agy"), "--model", "gemini-3.8-flash-low"])

    def test_routes_command_json(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            result = run_aicli("routes", "--json", config_path=config_path)
            self.assertEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertIn("maintenance", data["classes"])
            self.assertEqual(data["classes"]["maintenance"]["tool"], "agy")

    def test_route_set_and_remove(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            routes_path = Path(d) / "routes.json"
            env = {**os.environ, "AICLI_CONFIG": str(config_path), "AICLI_ROUTES": str(routes_path)}

            # Set class route
            res = subprocess.run([sys.executable, str(AICLI), "route", "set-class", "maintenance",
                                  "--tool", "claude", "--tier", "deep"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0)

            # Check argv reflects the update
            res = subprocess.run([sys.executable, str(AICLI), "argv", "--class", "maintenance", "--json"],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0)
            argv = json.loads(res.stdout)
            self.assertEqual(argv, [str(FAKE_CLI / "fake-claude"), "--model", "claude-opus-5-5"])

            # Set client route
            res = subprocess.run([sys.executable, str(AICLI), "route", "set-client", "pjm:maint",
                                  "--class", "maintenance", "--tool", "agy", "--tier", "low"],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0)
            res = subprocess.run([sys.executable, str(AICLI), "argv", "--client", "pjm:maint", "--json"],
                                 capture_output=True, text=True, env=env)
            argv = json.loads(res.stdout)
            self.assertEqual(argv, [str(FAKE_CLI / "fake-agy"), "--model", "gemini-3.8-flash-low"])

            # Remove client route
            res = subprocess.run([sys.executable, str(AICLI), "route", "remove-client", "pjm:maint"],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0)

    def test_route_set_client_rejects_unknown_class(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            routes_path = Path(d) / "routes.json"
            env = {**os.environ, "AICLI_CONFIG": str(config_path), "AICLI_ROUTES": str(routes_path)}
            res = subprocess.run([sys.executable, str(AICLI), "route", "set-client", "x:y", "--class", "nope"],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 2)
            self.assertIn("unknown workload class", res.stderr)
            self.assertFalse(routes_path.exists())

    def test_resolve_json(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            res = subprocess.run(
                [sys.executable, str(AICLI), "resolve", "--class", "standard-dev", "--json"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path)},
            )
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(data["class"], "standard-dev")
            self.assertEqual(data["tool"], "claude")
            self.assertEqual(data["model"], "claude-sonnet-5")
            self.assertIn("quota", data)

    def test_run_meta_out(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            meta_file = Path(d) / "run.meta.json"
            # FAKE_CLI fake-claude will be execv'd
            res = subprocess.run(
                [sys.executable, str(AICLI), "run", "--class", "standard-dev", "--client", "pjm:test:run-1",
                 "--meta-out", str(meta_file), "--", "echo", "hello"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path)},
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(meta_file.exists())
            data = json.loads(meta_file.read_text())
            self.assertEqual(data["client"], "pjm:test:run-1")
            self.assertEqual(data["class"], "standard-dev")
            self.assertEqual(data["tool"], "claude")
            self.assertEqual(data["model"], "claude-sonnet-5")
            self.assertIn("quota", data)

    def test_run_meta_out_reports_the_callers_own_model(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d))
            meta_file = Path(d) / "run.meta.json"
            res = subprocess.run(
                [sys.executable, str(AICLI), "run", "--tool", "claude", "--effort", "high",
                 "--meta-out", str(meta_file), "--", "--model", "claude-opus-5-5", "-p", "hi"],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path)},
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(meta_file.read_text())
            self.assertEqual(data["model"], "claude-opus-5-5")
            self.assertEqual(data["effort"], "high")

    def test_run_cli_not_found_writes_no_meta_or_usage(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, _ = make_config(Path(d), claude={"bin": str(Path(d) / "missing")})
            meta_file = Path(d) / "run.meta.json"
            usage_log = Path(d) / "usage.jsonl"
            res = subprocess.run(
                [sys.executable, str(AICLI), "run", "--tool", "claude", "--meta-out", str(meta_file)],
                capture_output=True, text=True,
                env={**os.environ, "AICLI_CONFIG": str(config_path), "PATH": "/nonexistent",
                     "AICLI_USAGE_LOG": str(usage_log)},
            )
            self.assertEqual(res.returncode, 1)
            self.assertFalse(meta_file.exists())
            self.assertFalse(usage_log.exists())

    def test_save_routes_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            routes_path = Path(d) / "routes.json"
            aicli.save_routes({"classes": {}, "clients": {}}, routes_path=routes_path)
            aicli.save_routes({"classes": {}, "clients": {"a": {}}}, routes_path=routes_path)
            self.assertEqual(json.loads(routes_path.read_text())["clients"], {"a": {}})
            self.assertEqual([p.name for p in Path(d).iterdir()], ["routes.json"])

    def test_resolve_route_hierarchical_client_matching(self):
        with tempfile.TemporaryDirectory() as d:
            config_path, config = make_config(Path(d))
            routes = {
                "classes": aicli.DEFAULT_CLASSES,
                "clients": {
                    "pjm:auto-execute": {"class": "standard-dev"},
                    "pjm:maintainer:routine": {"class": "maintenance"},
                    "pjm:scrum-master": {"class": "managerial-audit"},
                },
                "optiplex_projects": ["pjm", "homelab"],
            }
            # Test exact match
            tool, tier, effort, cls = aicli.resolve_route(config, client="pjm:scrum-master", routes=routes)
            self.assertEqual((tool, tier, cls), ("agy", "low", "managerial-audit"))

            # Test hierarchical match for ticket run
            tool, tier, effort, cls = aicli.resolve_route(config, client="pjm:p-0001:auto-execute", routes=routes)
            self.assertEqual((tool, tier, cls), ("claude", "default", "standard-dev"))

            # Test hierarchical match for maintainer run
            tool, tier, effort, cls = aicli.resolve_route(config, client="pjm:maintainer:homelab:routine", routes=routes)
            self.assertEqual((tool, tier, cls), ("agy", "low", "maintenance"))

    def test_optiplex_projects_load_and_save(self):
        with tempfile.TemporaryDirectory() as d:
            routes_file = Path(d) / "routes.json"
            routes = {
                "classes": {"test": {"tool": "agy", "tier": "low"}},
                "clients": {"c1": {"class": "test"}},
                "optiplex_projects": ["pjm", "homelab", "farah"],
            }
            aicli.save_routes(routes, routes_path=routes_file)
            loaded = aicli.load_routes(routes_path=routes_file)
            self.assertEqual(loaded["optiplex_projects"], ["pjm", "homelab", "farah"])
            self.assertIn("c1", loaded["clients"])


if __name__ == "__main__":
    unittest.main()

