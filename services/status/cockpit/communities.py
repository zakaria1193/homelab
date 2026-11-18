"""Parses the salsa-social communities config for the /communities overview
(homelab-0024, plan item 1). Nothing here imports or runs TypeScript: every
value is pulled out of `src/server/communities/<slug>.ts`, `index.ts` and
`docs/launch-checklists/<slug>.md` in the local clone with a small
regex/field parser, the same values and sections
`scripts/check-launch-checklist.ts` requires. A file this module cannot read
is reported with an "error" key and the rest of the page still renders.

Read-only: nothing here writes to the salsa-social clone. Editing and
creating a community is `cockpit/salsa_social_edit.py` (a later plan item)."""

import os
import re

SALSA_SOCIAL_DIR = os.path.expanduser(
    os.environ.get("STATUS_SALSA_SOCIAL_DIR") or "~/my_repos/salsa-social"
)

FEATURE_KEYS = ("attendanceTaps", "classes", "welcomeHosts", "map", "cityPages", "styleFilters")

# Mirrors scripts/check-launch-checklist.ts in the salsa-social repo: which
# sections are required for a `live` community, and the one section required
# for a `hidden` one.
LIVE_ONLY_SECTIONS = [
    "SEO",
    "AEO/GEO (AI answer engines)",
    "Performance budgets",
    "Accessibility",
    "Analytics",
]
HIDDEN_SECTION = "Hidden community (only for a `status: 'hidden'` community)"


def _communities_dir(salsa_dir):
    return os.path.join(salsa_dir, "src", "server", "communities")


def _checklists_dir(salsa_dir):
    return os.path.join(salsa_dir, "docs", "launch-checklists")


def _ci_yml_path(salsa_dir):
    return os.path.join(salsa_dir, ".github", "workflows", "ci.yml")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _string_field(text, name):
    m = re.search(r"%s:\s*'((?:[^'\\]|\\.)*)'" % re.escape(name), text)
    if not m:
        return None
    return m.group(1).replace("\\'", "'").replace("\\\\", "\\")


def _int_field(text, name):
    m = re.search(r"%s:\s*(\d+)" % re.escape(name), text)
    return int(m.group(1)) if m else None


def _hosts_field(text):
    m = re.search(r"hosts:\s*\[(.*?)\]", text, re.S)
    if not m:
        return []
    return re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))


def _features_field(text):
    m = re.search(r"features:\s*\{(.*?)\}", text, re.S)
    body = m.group(1) if m else ""
    return {key: bool(re.search(r"%s\s*:\s*true" % key, body)) for key in FEATURE_KEYS}


def _parse_community_file(slug, path, salsa_dir):
    try:
        text = _read(path)
    except OSError:
        rel = os.path.relpath(path, salsa_dir)
        return {"slug": slug, "error": "cannot read `%s`" % rel}
    return {
        "slug": slug,
        "id": _int_field(text, "id"),
        "name": _string_field(text, "name"),
        "origin": _string_field(text, "origin"),
        "hosts": _hosts_field(text),
        "status": _string_field(text, "status"),
        "features": _features_field(text),
        "ingestion": _string_field(text, "ingestion"),
        "error": "",
    }


def list_communities(salsa_dir=None):
    """Every entry of `COMMUNITIES`, in `index.ts`'s order. Returns
    `(communities, error)`; `error` is set only when `index.ts` itself
    cannot be read or parsed, since nothing else can be listed then."""
    salsa_dir = salsa_dir or SALSA_SOCIAL_DIR
    index_path = os.path.join(_communities_dir(salsa_dir), "index.ts")
    try:
        index_text = _read(index_path)
    except OSError:
        return [], "cannot read `src/server/communities/index.ts`"

    imports = dict(re.findall(r"import\s*\{\s*(\w+)\s*\}\s*from\s*'\./([\w-]+)\.ts'", index_text))
    m = re.search(r"COMMUNITIES[^=]*=\s*\[(.*?)\]", index_text, re.S)
    if not m:
        return [], "cannot find `COMMUNITIES` in `src/server/communities/index.ts`"
    order = [v.strip() for v in m.group(1).split(",") if v.strip()]

    communities = []
    for var in order:
        file_slug = imports.get(var, var)
        path = os.path.join(_communities_dir(salsa_dir), file_slug + ".ts")
        communities.append(_parse_community_file(file_slug, path, salsa_dir))
    return communities, ""


def _parse_checklist(markdown):
    items = []
    section = ""
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.*)$", line)
        if heading:
            section = heading.group(1).strip()
            continue
        item = re.match(r"^- \[( |x)\] (.*)$", line)
        if item:
            items.append({"section": section, "label": item.group(2).strip(), "checked": item.group(1) == "x"})
    return items


def _is_manual(label):
    return bool(re.search(r"\(manual\b", label, re.IGNORECASE))


def checklist_progress(slug, status, salsa_dir=None):
    """Required items checked out of required items for `status`, and how
    many more unchecked, non-manual `live`-only items stand between this
    community and `live` (0 once it already is)."""
    salsa_dir = salsa_dir or SALSA_SOCIAL_DIR
    path = os.path.join(_checklists_dir(salsa_dir), slug + ".md")
    try:
        items = _parse_checklist(_read(path))
    except OSError:
        return {"error": "cannot read `docs/launch-checklists/%s.md`" % slug}

    wanted_sections = LIVE_ONLY_SECTIONS if status == "live" else [HIDDEN_SECTION]
    required = [i for i in items if i["section"] in wanted_sections]
    checked = sum(1 for i in required if i["checked"])
    missing = [i["label"] for i in required if not i["checked"] and not _is_manual(i["label"])]

    live_required = [i for i in items if i["section"] in LIVE_ONLY_SECTIONS]
    live_missing = [i["label"] for i in live_required if not i["checked"] and not _is_manual(i["label"])]

    return {
        "required": len(required),
        "checked": checked,
        "missing": missing,
        "needed_for_live": 0 if status == "live" else len(live_missing),
        "error": "",
    }


def deploy_status(slug, is_default, salsa_dir=None):
    """Whether salsa-social's CI builds and deploys this community, judged
    only from local evidence: the slug in the `check-launch-checklist`
    arguments, a `wrangler pages deploy --project-name` step, and (for a
    non-default community) its own `wrangler.<slug>.toml`. A community
    without that local pipeline is "not deployed"; the hand steps list also
    always names the Cloudflare Pages project and the D1 row, since those
    can never be confirmed from the clone alone."""
    salsa_dir = salsa_dir or SALSA_SOCIAL_DIR
    try:
        ci_text = _read(_ci_yml_path(salsa_dir))
    except OSError:
        return {"deployed": False, "hand_steps": ["cannot read `.github/workflows/ci.yml`"]}

    checklist_slugs = set()
    checklist_line = re.search(r"check-launch-checklist[^\n]*--\s*(.+)", ci_text)
    if checklist_line:
        checklist_slugs = set(re.findall(r"([\w-]+)=\S+", checklist_line.group(1)))

    has_deploy_step = bool(re.search(r"wrangler pages deploy[^\n]*--project-name", ci_text))
    has_own_wrangler = is_default or os.path.exists(os.path.join(salsa_dir, "wrangler.%s.toml" % slug))

    deployed = slug in checklist_slugs and has_deploy_step and has_own_wrangler
    if deployed:
        return {"deployed": True, "hand_steps": []}

    hand_steps = []
    if not has_deploy_step:
        hand_steps.append("a build step and a `wrangler pages deploy --project-name <name>` step in ci.yml")
    if not has_own_wrangler:
        hand_steps.append("its own `wrangler.%s.toml`" % slug)
    if slug not in checklist_slugs:
        hand_steps.append("its slug in the check-launch-checklist arguments in ci.yml")
    hand_steps.append("a Cloudflare Pages project")
    hand_steps.append("its row in D1")
    return {"deployed": False, "hand_steps": hand_steps}


def overview(salsa_dir=None):
    """Everything the /communities page shows except the D1 counts (kept in
    `cockpit/d1_client.py`, called separately per community id)."""
    salsa_dir = salsa_dir or SALSA_SOCIAL_DIR
    communities, index_error = list_communities(salsa_dir)
    if index_error:
        return {"communities": [], "error": index_error}

    rows = []
    for i, community in enumerate(communities):
        row = dict(community)
        if not row.get("error"):
            row["checklist"] = checklist_progress(row["slug"], row["status"], salsa_dir)
            row["deploy"] = deploy_status(row["slug"], is_default=(i == 0), salsa_dir=salsa_dir)
        rows.append(row)
    return {"communities": rows, "error": ""}
