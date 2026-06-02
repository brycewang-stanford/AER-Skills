#!/usr/bin/env python3
"""Repository checks for the AER-skills bundle.

The checks intentionally avoid third-party Python packages so they can run in
fresh CI environments and on a local machine before copying skills into an
agent profile.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,63}$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HTML_LOCAL_ATTR_RE = re.compile(r"""\b(?:href|src)=["']([^"']+)["']""")
BACKTICK_RE = re.compile(r"`([^`]+)`")
BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
BIB_KEY_CANDIDATE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:19|20)\d{2}$")
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
MD_LINK_TEXT_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ANCHOR_RE = re.compile(r"""<[^>]+\s(?:id|name)=["']([^"']+)["']""", re.IGNORECASE)
REQUIRED_AGENT_FIELDS = ("display_name", "short_description", "default_prompt")
AGENT_FIELD_LIMITS = {
    "display_name": (4, 64),
    "short_description": (25, 64),
    "default_prompt": (20, 180),
}
ALLOWED_SKILL_TOP_LEVEL = {"SKILL.md", "agents", "scripts", "references", "assets"}
BANNED_SKILL_FILENAMES = {
    "README.md",
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md",
    "CHANGELOG.md",
}
MAX_SKILL_MD_LINES = 500
REQUIRED_CLI_SCRIPTS = (
    ROOT / "scripts" / "install_skills.py",
    ROOT / "scripts" / "scaffold_project.py",
    ROOT / "scripts" / "validate_repo.py",
)
EXPECTED_TEMPLATE_FILES = {
    "stata": {
        "00_globals.do",
        "00_install_packages.do",
        "01_clean.do",
        "02_descriptives.do",
        "03_main_did.do",
        "04_robustness.do",
        "05_heterogeneity.do",
        "06_tables.do",
        "07_figures.do",
        "README.md",
        "run_all.do",
    },
    "r": {
        "00_setup.R",
        "01_clean.R",
        "02_descriptives.R",
        "03_main_did.R",
        "04_robustness.R",
        "05_heterogeneity.R",
        "06_tables.R",
        "07_figures.R",
        "README.md",
        "run_all.R",
    },
    "python": {
        "clean.py",
        "descriptives.py",
        "figures.py",
        "heterogeneity.py",
        "main_did.py",
        "README.md",
        "requirements.txt",
        "robustness.py",
        "run_all.py",
        "setup.py",
        "tables.py",
    },
}
EXPECTED_SKELETON_CODE_FILES = {
    "00_globals.do",
    "00_install_packages.do",
    "01_clean.do",
    "02_descriptives.do",
    "03_main_did.do",
    "04_robustness.do",
    "05_heterogeneity.do",
    "06_tables.do",
    "07_figures.do",
}
EXPECTED_EXAMPLE_DEMOS = {
    "staggered-did-demo": {
        "README.md",
        "staggered_did_demo.R",
        "staggered_did_demo.py",
    },
}
TEXT_SUFFIXES = {
    "",
    ".bib",
    ".do",
    ".json",
    ".md",
    ".py",
    ".r",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}
GENERATED_OR_CACHE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "logs",
    "node_modules",
    "output",
    "venv",
}
LOCAL_PATH_MARKERS = (
    "/" + "Users" + "/",
    "/" + "home" + "/",
    "C:" + "\\" + "Users" + "\\",
    "/" + "var" + "/" + "folders" + "/",
)
REQUIRED_POLICY_PHRASES = {
    ROOT / "README.md": (
        "100 words",
        "7,000 words minus 200 per exhibit",
        "AEA Data and Code Availability Policy",
    ),
    ROOT / "README.zh-CN.md": (
        "7,000",
        "6,000",
        "Disclosure statements",
    ),
    ROOT / "skills" / "aer-submission" / "SKILL.md": (
        "100 words",
        "7,000 words minus 200 per exhibit",
        "Disclosure Statement PDFs",
        "AI usage disclosure",
    ),
    ROOT / "skills" / "aer-replication" / "SKILL.md": (
        "February 2026",
        "Data and Code Availability Statement",
        "README.pdf",
        "openICPSR",
    ),
    ROOT / "docs" / "desk-rejection-audit.md": (
        "100 words",
        "7,000 words",
        "openICPSR-ready",
    ),
}
INSTALL_DOC_GUARDRAIL_PHRASES = {
    ROOT / "docs" / "installation-codex.md": (
        "Do not pass a repository source directory",
        "the installer refuses those destinations",
    ),
    ROOT / "docs" / "installation-claude.md": (
        "Do not pass a repository source directory",
        "Project-scoped installs",
        "should use `.claude/skills`",
    ),
}
REQUIRED_RESOURCE_LINKS = {
    ROOT / "skills" / "aer-identification" / "SKILL.md": (
        "docs/methods-reference.md",
        "examples/modern-aer-exemplars.md",
    ),
    ROOT / "skills" / "aer-robustness" / "SKILL.md": (
        "docs/methods-reference.md",
        "templates/stata/04_robustness.do",
        "templates/stata/05_heterogeneity.do",
    ),
}


class ValidationError(Exception):
    """Raised when one or more repository checks fail."""


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def parse_frontmatter(path: Path, errors: list[str]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        fail(errors, f"{rel(path)}: missing YAML frontmatter")
        return {}

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            fail(errors, f"{rel(path)}: invalid frontmatter line: {line!r}")
            continue
        fields[key.strip()] = value.strip().strip('"')
    return fields


def parse_agent_yaml(path: Path, errors: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_interface = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line == "interface:":
            in_interface = True
            continue
        if in_interface and raw_line.startswith("  "):
            key, sep, value = raw_line.strip().partition(":")
            if sep:
                fields[key] = value.strip().strip('"')
            continue
        fail(errors, f"{rel(path)}: unsupported YAML shape near {raw_line!r}")

    if not in_interface:
        fail(errors, f"{rel(path)}: missing top-level interface block")
    return fields


def check_skills(errors: list[str]) -> list[str]:
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        fail(errors, "skills/: directory missing")
        return []

    skill_names: list[str] = []
    display_names: dict[str, str] = {}
    short_descriptions: dict[str, str] = {}
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        name = skill_dir.name
        skill_names.append(name)
        if not SKILL_NAME_RE.fullmatch(name):
            fail(errors, f"{rel(skill_dir)}: invalid skill directory name")

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            fail(errors, f"{rel(skill_dir)}: missing SKILL.md")
            continue

        for child in sorted(skill_dir.iterdir()):
            if child.name not in ALLOWED_SKILL_TOP_LEVEL:
                fail(errors, f"{rel(child)}: unexpected top-level skill file or directory")
        for banned_file in sorted(
            path for path in skill_dir.rglob("*") if path.name in BANNED_SKILL_FILENAMES
        ):
            fail(errors, f"{rel(banned_file)}: auxiliary docs should not live inside skills/")
        line_count = len(skill_md.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_SKILL_MD_LINES:
            fail(
                errors,
                f"{rel(skill_md)}: {line_count} lines exceeds {MAX_SKILL_MD_LINES}-line limit",
            )

        frontmatter = parse_frontmatter(skill_md, errors)
        if set(frontmatter) != {"name", "description"}:
            fail(
                errors,
                f"{rel(skill_md)}: frontmatter must contain only name and description",
            )
        if frontmatter.get("name") != name:
            fail(errors, f"{rel(skill_md)}: name does not match directory")
        description = frontmatter.get("description", "")
        if "Use when" not in description:
            fail(errors, f"{rel(skill_md)}: description should include trigger context")

        agent_yaml = skill_dir / "agents" / "openai.yaml"
        if not agent_yaml.is_file():
            fail(errors, f"{rel(skill_dir)}: missing agents/openai.yaml")
            continue
        agent_fields = parse_agent_yaml(agent_yaml, errors)
        for field in REQUIRED_AGENT_FIELDS:
            if not agent_fields.get(field):
                fail(errors, f"{rel(agent_yaml)}: missing interface.{field}")
                continue
            value = agent_fields[field]
            minimum, maximum = AGENT_FIELD_LIMITS[field]
            if not minimum <= len(value) <= maximum:
                fail(
                    errors,
                    f"{rel(agent_yaml)}: interface.{field} should be {minimum}-{maximum} characters",
                )
            if "\n" in value or "\r" in value:
                fail(errors, f"{rel(agent_yaml)}: interface.{field} should be one line")
            if "[" in value or "](" in value:
                fail(errors, f"{rel(agent_yaml)}: interface.{field} should be plain text")
        default_prompt = agent_fields.get("default_prompt", "")
        if f"${name}" not in default_prompt:
            fail(errors, f"{rel(agent_yaml)}: default_prompt should invoke ${name}")
        if default_prompt and not default_prompt.startswith(f"Use ${name} "):
            fail(errors, f"{rel(agent_yaml)}: default_prompt should start with Use ${name}")

        display_name = agent_fields.get("display_name", "")
        if display_name:
            if display_name in display_names:
                fail(
                    errors,
                    f"{rel(agent_yaml)}: duplicate display_name also used by {display_names[display_name]}",
                )
            display_names[display_name] = rel(agent_yaml)
        short_description = agent_fields.get("short_description", "")
        if short_description:
            if short_description in short_descriptions:
                fail(
                    errors,
                    f"{rel(agent_yaml)}: duplicate short_description also used by "
                    f"{short_descriptions[short_description]}",
                )
            short_descriptions[short_description] = rel(agent_yaml)

    return skill_names


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(errors, f"{rel(path)}: invalid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        fail(errors, f"{rel(path)}: expected top-level JSON object")
        return {}
    return data


def require_json_string(document: dict, path: Path, key: str, errors: list[str]) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(errors, f"{rel(path)}: missing {key}")
        return ""
    return value


def require_json_object(document: dict, path: Path, key: str, errors: list[str]) -> dict:
    value = document.get(key)
    if not isinstance(value, dict):
        fail(errors, f"{rel(path)}: missing {key} object")
        return {}
    return value


def check_plugin_manifest(skill_names: list[str], errors: list[str]) -> None:
    plugin_json = ROOT / ".claude-plugin" / "plugin.json"
    marketplace_json = ROOT / ".claude-plugin" / "marketplace.json"
    for path in (plugin_json, marketplace_json):
        if not path.is_file():
            fail(errors, f"{rel(path)}: missing")

    plugin = load_json(plugin_json, errors) if plugin_json.is_file() else {}
    marketplace = load_json(marketplace_json, errors) if marketplace_json.is_file() else {}

    expected_paths = [f"skills/{name}" for name in skill_names]
    for key in ("name", "description", "version", "license", "homepage", "repository"):
        require_json_string(plugin, plugin_json, key, errors)
    author = require_json_object(plugin, plugin_json, "author", errors)
    for key in ("name", "email"):
        value = author.get(key)
        if not isinstance(value, str) or not value.strip():
            fail(errors, f"{rel(plugin_json)}: missing author.{key}")

    for key in ("name", "version", "description"):
        require_json_string(marketplace, marketplace_json, key, errors)
    owner = require_json_object(marketplace, marketplace_json, "owner", errors)
    if owner != author:
        fail(errors, f"{rel(marketplace_json)}: owner does not match plugin.json author")

    metadata = marketplace.get("metadata")
    if not isinstance(metadata, dict):
        fail(errors, f"{rel(marketplace_json)}: missing metadata object")
    elif metadata.get("pluginRoot") != "./":
        fail(errors, f"{rel(marketplace_json)}: metadata.pluginRoot should be ./")

    for key in ("name", "version"):
        if plugin.get(key) != marketplace.get(key):
            fail(errors, f"{rel(marketplace_json)}: {key} does not match plugin.json")

    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        fail(errors, f"{rel(marketplace_json)}: expected exactly one plugin entry")
        return

    entry = plugins[0]
    if not isinstance(entry, dict):
        fail(errors, f"{rel(marketplace_json)}: plugin entry should be an object")
        return

    for key in ("name", "version", "license", "homepage", "repository"):
        if entry.get(key) != plugin.get(key):
            fail(errors, f"{rel(marketplace_json)}: plugin entry {key} does not match plugin.json")
    if entry.get("author") != author:
        fail(errors, f"{rel(marketplace_json)}: plugin entry author does not match plugin.json")
    if entry.get("source") != "./":
        fail(errors, f"{rel(marketplace_json)}: plugin entry source should be ./")

    listed = entry.get("skills")
    if not isinstance(listed, list):
        fail(errors, f"{rel(marketplace_json)}: plugin entry skills should be a list")
        return
    string_paths = [skill_path for skill_path in listed if isinstance(skill_path, str)]
    duplicate_paths = sorted(path for path in set(string_paths) if string_paths.count(path) > 1)
    if duplicate_paths:
        fail(errors, f"{rel(marketplace_json)}: duplicate skill paths: {', '.join(duplicate_paths)}")
    if sorted(string_paths) != sorted(expected_paths) or len(string_paths) != len(listed):
        fail(
            errors,
            f"{rel(marketplace_json)}: skills list does not match skills/ directories",
        )
    for skill_path in listed:
        if not isinstance(skill_path, str):
            fail(errors, f"{rel(marketplace_json)}: skill path should be a string")
            continue
        if not (ROOT / skill_path / "SKILL.md").is_file():
            fail(errors, f"{rel(marketplace_json)}: missing listed skill {skill_path}/SKILL.md")


def check_skill_reference_docs(skill_names: list[str], errors: list[str]) -> None:
    readme_paths = (ROOT / "README.md", ROOT / "README.zh-CN.md")
    for path in readme_paths:
        text = path.read_text(encoding="utf-8")
        for name in skill_names:
            link = f"skills/{name}/SKILL.md"
            if link not in text:
                fail(errors, f"{rel(path)}: missing link to {link}")

    workflow_map = ROOT / "docs" / "workflow-map.md"
    text = workflow_map.read_text(encoding="utf-8")
    for name in skill_names:
        if name not in text:
            fail(errors, f"{rel(workflow_map)}: missing {name}")

    primary_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    if "examples/README.md" not in primary_readme:
        fail(errors, "README.md: missing link to examples/README.md")

    required_docs = (
        "desk-rejection-audit.md",
        "methods-reference.md",
        "source-register.md",
    )
    for doc in required_docs:
        readme_link = f"docs/{doc}"
        workflow_link = f"./{doc}"
        if readme_link not in primary_readme:
            fail(errors, f"README.md: missing link to {readme_link}")
        if readme_link not in chinese_readme:
            fail(errors, f"README.zh-CN.md: missing link to {readme_link}")
        if workflow_link not in text:
            fail(errors, f"{rel(workflow_map)}: missing link to {workflow_link}")

    examples_readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    for doc in ("../docs/methods-reference.md", "../docs/desk-rejection-audit.md"):
        if doc not in examples_readme:
            fail(errors, f"examples/README.md: missing link to {doc}")


def check_source_register(errors: list[str]) -> None:
    source_register = ROOT / "docs" / "source-register.md"
    if not source_register.is_file():
        fail(errors, f"{rel(source_register)}: missing")
        return

    text = source_register.read_text(encoding="utf-8")
    required_sources = (
        "https://www.aeaweb.org/journals/aer/submissions",
        "https://www.aeaweb.org/journals/aer/accepted-article-guidelines",
        "https://www.aeaweb.org/journals/aeri/submissions",
        "https://www.aeaweb.org/journals/aeri/accepted-article-guidelines",
        "https://www.aeaweb.org/journals/data/data-code-policy",
        "https://www.aeaweb.org/journals/forms/data-code-availability",
        "https://www.icpsr.umich.edu/sites/aea/home",
    )
    for source in required_sources:
        if source not in text:
            fail(errors, f"{rel(source_register)}: missing official source {source}")

    for phrase in ("Last reviewed:", "Repo surfaces", "Review trigger"):
        if phrase not in text:
            fail(errors, f"{rel(source_register)}: missing {phrase!r}")

    for match in BACKTICK_RE.finditer(text):
        candidate = match.group(1)
        if " " in candidate or candidate.startswith(("http://", "https://")):
            continue
        if candidate.endswith((".md", ".py", ".bib", "/")):
            resolved = ROOT / candidate.rstrip("/")
            if not resolved.exists():
                fail(errors, f"{rel(source_register)}: listed surface does not exist: {candidate}")


def check_policy_guardrails(errors: list[str]) -> None:
    """Catch accidental deletion of high-risk journal-policy constraints."""

    for path, phrases in REQUIRED_POLICY_PHRASES.items():
        if not path.is_file():
            fail(errors, f"{rel(path)}: missing policy-bearing file")
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                fail(errors, f"{rel(path)}: missing policy guardrail phrase {phrase!r}")


def check_installation_guardrails(errors: list[str]) -> None:
    """Keep installer safety behavior documented for manual users."""

    for path, phrases in INSTALL_DOC_GUARDRAIL_PHRASES.items():
        if not path.is_file():
            fail(errors, f"{rel(path)}: missing installation guide")
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                fail(errors, f"{rel(path)}: missing installer guardrail phrase {phrase!r}")


def check_skill_resource_links(errors: list[str]) -> None:
    """Keep core skills tied to runnable templates and citation-backed docs."""

    for path, resources in REQUIRED_RESOURCE_LINKS.items():
        if not path.is_file():
            fail(errors, f"{rel(path)}: missing skill file")
            continue
        text = path.read_text(encoding="utf-8")
        for resource in resources:
            if resource not in text:
                fail(errors, f"{rel(path)}: missing repository resource {resource}")
            if not (ROOT / resource).exists():
                fail(errors, f"{rel(path)}: listed repository resource missing: {resource}")


def check_bibliography_integrity(errors: list[str]) -> None:
    references = ROOT / "references.bib"
    methods_reference = ROOT / "docs" / "methods-reference.md"
    if not references.is_file():
        fail(errors, f"{rel(references)}: missing")
        return
    if not methods_reference.is_file():
        fail(errors, f"{rel(methods_reference)}: missing")
        return

    bib_text = references.read_text(encoding="utf-8")
    keys = BIB_ENTRY_RE.findall(bib_text)
    if not keys:
        fail(errors, f"{rel(references)}: no BibTeX entries found")
        return

    seen: dict[str, int] = {}
    for key in keys:
        if key in seen:
            fail(errors, f"{rel(references)}: duplicate BibTeX key {key!r}")
        seen[key] = seen.get(key, 0) + 1

    for entry in re.split(r"\n(?=@\w+\s*\{)", bib_text):
        match = BIB_ENTRY_RE.search(entry)
        if not match:
            continue
        key = match.group(1)
        if "doi" not in entry.lower() and "No Crossref DOI" not in entry:
            fail(errors, f"{rel(references)}: {key} missing DOI or explicit no-DOI note")

    method_text = methods_reference.read_text(encoding="utf-8")
    bib_keys = set(keys)
    for match in BACKTICK_RE.finditer(method_text):
        candidate = match.group(1)
        if BIB_KEY_CANDIDATE_RE.fullmatch(candidate) and candidate not in bib_keys:
            fail(
                errors,
                f"{rel(methods_reference)}: citation key {candidate!r} missing from references.bib",
            )


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in GENERATED_OR_CACHE_DIRS for part in path.parts)
    )


def text_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in GENERATED_OR_CACHE_DIRS for part in path.parts)
        and path.suffix.lower() in TEXT_SUFFIXES
    )


def normalize_markdown_target(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target and not target.startswith(("./", "../")):
        target = target.split()[0]
    return unquote(target)


def github_heading_slug(heading: str) -> str:
    heading = re.sub(r"`([^`]*)`", r"\1", heading.strip())
    heading = MD_LINK_TEXT_RE.sub(r"\1", heading)
    heading = HTML_TAG_RE.sub("", heading)
    heading = re.sub(r"\s+#*$", "", heading).lower()
    cleaned = "".join(
        character
        for character in heading
        if character.isalnum() or character.isspace() or character in "-_"
    )
    return re.sub(r"\s", "-", cleaned.strip())


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for match in HTML_ANCHOR_RE.finditer(text):
        anchors.add(unquote(match.group(1)).strip().lower())

    for line in text.splitlines():
        match = MD_HEADING_RE.match(line)
        if not match:
            continue
        base = github_heading_slug(match.group(2))
        suffix = seen.get(base, 0)
        seen[base] = suffix + 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def check_validator_self_tests(errors: list[str]) -> None:
    slug_cases = {
        "1. Difference-in-differences (staggered adoption)": (
            "1-difference-in-differences-staggered-adoption"
        ),
        "3. Shift-share / Bartik": "3-shift-share--bartik",
        "AER: Insights `word-count` PDF": "aer-insights-word-count-pdf",
        "[methods reference](./methods-reference.md)": "methods-reference",
    }
    for heading, expected in slug_cases.items():
        actual = github_heading_slug(heading)
        if actual != expected:
            fail(
                errors,
                f"validator: heading slug for {heading!r} was {actual!r}, expected {expected!r}",
            )

    with tempfile.TemporaryDirectory() as tempdir:
        fixture = Path(tempdir) / "anchors.md"
        fixture.write_text(
            "\n".join(
                [
                    "# Methods Reference",
                    "## Methods Reference",
                    "<a id=\"custom-anchor\"></a>",
                    "<span name=\"legacy-anchor\"></span>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        actual_anchors = markdown_anchors(fixture)
        expected_anchors = {
            "methods-reference",
            "methods-reference-1",
            "custom-anchor",
            "legacy-anchor",
        }
        missing = sorted(expected_anchors - actual_anchors)
        if missing:
            fail(errors, f"validator: markdown anchor self-test missed {', '.join(missing)}")


def check_markdown_links(errors: list[str]) -> None:
    anchor_cache: dict[Path, set[str]] = {}

    def check_local_target(path: Path, raw_target: str) -> None:
        raw_target = normalize_markdown_target(raw_target)
        if not raw_target or raw_target.startswith(("http://", "https://", "mailto:")):
            return

        local_target, _, anchor = raw_target.partition("#")
        if not local_target:
            resolved = path
        else:
            resolved = (path.parent / local_target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            fail(errors, f"{rel(path)}: link escapes repository: {raw_target}")
            return
        if not resolved.exists():
            fail(errors, f"{rel(path)}: broken local link: {raw_target}")
            return
        if anchor and resolved.suffix.lower() == ".md":
            anchor_id = unquote(anchor).strip().lower()
            if resolved not in anchor_cache:
                anchor_cache[resolved] = markdown_anchors(resolved)
            if anchor_id not in anchor_cache[resolved]:
                fail(errors, f"{rel(path)}: broken markdown anchor: {raw_target}")

    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in MD_LINK_RE.finditer(text):
            check_local_target(path, match.group(1))
        for match in HTML_LOCAL_ATTR_RE.finditer(text):
            check_local_target(path, match.group(1))


def run_command(args: list[str], errors: list[str], label: str) -> None:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        output = result.stdout.strip()
        fail(errors, f"{label} failed with exit {result.returncode}\n{output}")


def check_expected_file_set(path: Path, expected: set[str], errors: list[str]) -> None:
    if not path.is_dir():
        fail(errors, f"{rel(path)}: directory missing")
        return
    actual = {child.name for child in path.iterdir() if child.is_file()}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        fail(errors, f"{rel(path)}: missing expected files: {', '.join(missing)}")
    if extra:
        fail(errors, f"{rel(path)}: unexpected files: {', '.join(extra)}")


def check_template_layout(errors: list[str]) -> None:
    for template_name, expected in EXPECTED_TEMPLATE_FILES.items():
        check_expected_file_set(ROOT / "templates" / template_name, expected, errors)

    stata_steps = sorted(
        name for name in EXPECTED_TEMPLATE_FILES["stata"] if name.endswith(".do")
    )
    r_steps = sorted(name for name in EXPECTED_TEMPLATE_FILES["r"] if name.endswith(".R"))
    python_modules = sorted(
        path.stem
        for path in (ROOT / "templates" / "python").glob("*.py")
        if path.name != "run_all.py"
    )

    stata_run_all = (ROOT / "templates" / "stata" / "run_all.do").read_text(
        encoding="utf-8"
    )
    for step in stata_steps:
        if step != "run_all.do" and f'"{step}"' not in stata_run_all:
            fail(errors, f"templates/stata/run_all.do: missing do step {step}")

    r_run_all = (ROOT / "templates" / "r" / "run_all.R").read_text(encoding="utf-8")
    for step in r_steps:
        if step != "run_all.R" and f'"{step}"' not in r_run_all:
            fail(errors, f"templates/r/run_all.R: missing source step {step}")

    python_run_all = (ROOT / "templates" / "python" / "run_all.py").read_text(
        encoding="utf-8"
    )
    for module in python_modules:
        if module not in {"setup"} and f"import {module}" not in python_run_all:
            fail(errors, f"templates/python/run_all.py: missing import {module}")

    skeleton = ROOT / "examples" / "replication-package-skeleton"
    check_expected_file_set(skeleton / "code", EXPECTED_SKELETON_CODE_FILES, errors)
    skeleton_top_level = {child.name for child in skeleton.iterdir() if child.is_file()}
    expected_top_level = {"LICENSE", "README.md", "run_all.do"}
    missing = sorted(expected_top_level - skeleton_top_level)
    if missing:
        fail(errors, f"{rel(skeleton)}: missing expected files: {', '.join(missing)}")

    skeleton_run_all = (skeleton / "run_all.do").read_text(encoding="utf-8")
    for step in sorted(EXPECTED_SKELETON_CODE_FILES):
        if f'"code/{step}"' not in skeleton_run_all:
            fail(errors, f"{rel(skeleton / 'run_all.do')}: missing do step code/{step}")


def check_example_demos(errors: list[str]) -> None:
    examples_readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    tracked_examples = set(
        subprocess.run(
            ["git", "ls-files", "examples"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        ).stdout.splitlines()
    )
    for artifact in sorted((ROOT / "examples").iterdir()):
        if artifact.name == "README.md" or artifact.name.startswith("."):
            continue
        artifact_rel = rel(artifact)
        if artifact.is_file() and artifact_rel not in tracked_examples:
            continue
        if artifact.is_dir() and not any(
            tracked.startswith(f"{artifact_rel}/") for tracked in tracked_examples
        ):
            continue
        if artifact.is_file() and artifact.suffix != ".md":
            continue
        if artifact.is_dir() and not any(
            child.is_file() and not any(part in GENERATED_OR_CACHE_DIRS for part in child.parts)
            for child in artifact.rglob("*")
        ):
            continue
        if any(part in GENERATED_OR_CACHE_DIRS for part in artifact.parts):
            continue
        link_target = f"{artifact.name}/" if artifact.is_dir() else artifact.name
        if f"]({link_target})" not in examples_readme:
            fail(errors, f"examples/README.md: missing link to {link_target}")

    for demo_name, expected_files in EXPECTED_EXAMPLE_DEMOS.items():
        demo_dir = ROOT / "examples" / demo_name
        if not demo_dir.is_dir():
            fail(errors, f"{rel(demo_dir)}: demo directory missing")
            continue
        check_expected_file_set(demo_dir, expected_files, errors)
        if f"{demo_name}/" not in examples_readme:
            fail(errors, f"examples/README.md: missing link to {demo_name}/")


def check_python_templates(errors: list[str]) -> None:
    py_files = sorted((ROOT / "templates" / "python").glob("*.py"))
    py_files.extend(sorted((ROOT / "scripts").glob("*.py")))
    py_files.extend(sorted((ROOT / "examples").rglob("*.py")))
    for path in py_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            fail(errors, f"{rel(path)}: Python syntax error: {exc}")


def check_cli_scripts(errors: list[str]) -> None:
    for path in REQUIRED_CLI_SCRIPTS:
        if not path.is_file():
            fail(errors, f"{rel(path)}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("#!/usr/bin/env python3\n"):
            fail(errors, f"{rel(path)}: missing python3 shebang")
        if "if __name__ == \"__main__\":" not in text:
            fail(errors, f"{rel(path)}: missing __main__ guard")
        if "argparse.ArgumentParser" not in text:
            fail(errors, f"{rel(path)}: missing argparse CLI")


def check_r_templates(errors: list[str], require_optional_tools: bool) -> None:
    rscript = shutil.which("Rscript")
    if not rscript:
        message = "Rscript not found; skipping R template parse check"
        if require_optional_tools:
            fail(errors, message)
        else:
            print(f"warning: {message}", file=sys.stderr)
        return

    expression = (
        'files <- c(list.files("templates/r", pattern="[.]R$", full.names=TRUE), '
        'list.files("examples", pattern="[.]R$", full.names=TRUE, recursive=TRUE)); '
        'for (f in files) { parse(f); cat("OK", f, "\\n") }'
    )
    run_command([rscript, "-e", expression], errors, "R template parse")


def check_stata_templates(errors: list[str]) -> None:
    do_files = sorted((ROOT / "templates" / "stata").glob("*.do"))
    do_files.extend(
        sorted((ROOT / "examples" / "replication-package-skeleton").rglob("*.do"))
    )
    for path in do_files:
        text = path.read_text(encoding="utf-8")
        if "version 18.0" not in text:
            fail(errors, f"{rel(path)}: missing Stata version declaration")
        if path.name == "00_globals.do" and 'global project "`c(pwd)\'"' not in text:
            fail(errors, f"{rel(path)}: project root should come from c(pwd)")


def check_installer(errors: list[str]) -> None:
    installer = ROOT / "scripts" / "install_skills.py"
    if not installer.is_file():
        fail(errors, f"{rel(installer)}: missing")
        return

    expected = sorted(path.name for path in (ROOT / "skills").glob("aer-*") if path.is_dir())
    with tempfile.TemporaryDirectory() as tempdir:
        destination = Path(tempdir) / "skills"
        result = subprocess.run(
            [
                sys.executable,
                str(installer),
                "codex",
                "--dest",
                str(destination),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            fail(errors, f"{rel(installer)} smoke test failed\n{result.stdout.strip()}")
            return
        installed = sorted(path.name for path in destination.glob("aer-*") if path.is_dir())
        if installed != expected:
            fail(errors, f"{rel(installer)} smoke test installed wrong skill set")
            return
        for name in installed:
            if not (destination / name / "SKILL.md").is_file():
                fail(errors, f"{rel(installer)} smoke test missed {name}/SKILL.md")

        second_run = subprocess.run(
            [
                sys.executable,
                str(installer),
                "codex",
                "--dest",
                str(destination),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if second_run.returncode != 0:
            fail(errors, f"{rel(installer)} existing-install smoke test failed")
        if "skip existing" not in second_run.stdout:
            fail(errors, f"{rel(installer)} should skip existing installs by default")

        source_dest = subprocess.run(
            [
                sys.executable,
                str(installer),
                "codex",
                "--dest",
                str(ROOT / "skills"),
                "--replace",
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if source_dest.returncode == 0:
            fail(errors, f"{rel(installer)} should refuse installing into source skills/")

        repo_root_dest = subprocess.run(
            [
                sys.executable,
                str(installer),
                "codex",
                "--dest",
                str(ROOT),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if repo_root_dest.returncode == 0:
            fail(errors, f"{rel(installer)} should refuse repository root destination")

        repo_child_dest = subprocess.run(
            [
                sys.executable,
                str(installer),
                "codex",
                "--dest",
                str(ROOT / "docs"),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if repo_child_dest.returncode == 0:
            fail(errors, f"{rel(installer)} should refuse repository-internal destination")

        project_scoped_dest = subprocess.run(
            [
                sys.executable,
                str(installer),
                "claude",
                "--dest",
                str(ROOT / ".claude" / "skills"),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if project_scoped_dest.returncode != 0:
            fail(errors, f"{rel(installer)} should allow project-scoped .claude/skills dry-run")
        if "install" not in project_scoped_dest.stdout:
            fail(errors, f"{rel(installer)} project-scoped dry-run should preview installs")


def check_scaffolder(errors: list[str]) -> None:
    scaffolder = ROOT / "scripts" / "scaffold_project.py"
    if not scaffolder.is_file():
        fail(errors, f"{rel(scaffolder)}: missing")
        return

    expected_files = {
        "stata": "run_all.do",
        "r": "run_all.R",
        "python": "run_all.py",
        "skeleton": "run_all.do",
    }
    skeleton_dirs = (
        "data/raw",
        "data/intermediate",
        "data/codebook",
        "docs",
        "logs",
        "output/tables",
        "output/figures",
    )
    skeleton_source = ROOT / "examples" / "replication-package-skeleton"
    for directory in skeleton_dirs:
        keep_file = skeleton_source / directory / ".gitkeep"
        if not keep_file.is_file():
            fail(errors, f"{rel(keep_file)}: missing skeleton directory placeholder")

    with tempfile.TemporaryDirectory() as tempdir:
        base = Path(tempdir)
        for kind, expected_file in expected_files.items():
            destination = base / kind
            result = subprocess.run(
                [
                    sys.executable,
                    str(scaffolder),
                    kind,
                    str(destination),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                fail(errors, f"{rel(scaffolder)} {kind} smoke test failed\n{result.stdout.strip()}")
                continue
            if not (destination / expected_file).is_file():
                fail(errors, f"{rel(scaffolder)} {kind} smoke test missed {expected_file}")
            if kind == "skeleton":
                for directory in skeleton_dirs:
                    if not (destination / directory).is_dir():
                        fail(
                            errors,
                            f"{rel(scaffolder)} skeleton smoke test missed {directory}/",
                        )

        non_empty = base / "non-empty"
        non_empty.mkdir()
        (non_empty / "README.md").write_text("existing\n", encoding="utf-8")
        refused = subprocess.run(
            [
                sys.executable,
                str(scaffolder),
                "python",
                str(non_empty),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if refused.returncode == 0:
            fail(errors, f"{rel(scaffolder)} should refuse non-empty destination by default")

        source_refused = subprocess.run(
            [
                sys.executable,
                str(scaffolder),
                "stata",
                str(ROOT / "templates" / "stata"),
                "--replace",
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if source_refused.returncode == 0:
            fail(errors, f"{rel(scaffolder)} should refuse template source destination")

        nested_refused = subprocess.run(
            [
                sys.executable,
                str(scaffolder),
                "stata",
                str(ROOT / "templates" / "stata" / "nested-output"),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if nested_refused.returncode == 0:
            fail(errors, f"{rel(scaffolder)} should refuse destination inside template source")

        protected_refused = subprocess.run(
            [
                sys.executable,
                str(scaffolder),
                "stata",
                str(ROOT),
                "--replace",
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if protected_refused.returncode == 0:
            fail(errors, f"{rel(scaffolder)} should refuse replacing repository root")

        repo_child_refused = subprocess.run(
            [
                sys.executable,
                str(scaffolder),
                "stata",
                str(ROOT / "docs" / "scaffold-output"),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if repo_child_refused.returncode == 0:
            fail(errors, f"{rel(scaffolder)} should refuse repository-internal destinations")


def check_requirements(errors: list[str]) -> None:
    requirements = ROOT / "templates" / "python" / "requirements.txt"
    seen: dict[str, int] = {}
    for lineno, raw_line in enumerate(requirements.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            fail(errors, f"{rel(requirements)}:{lineno}: dependency is not exactly pinned")
            continue
        package = line.split("==", 1)[0].strip().lower()
        if package in seen:
            fail(errors, f"{rel(requirements)}:{lineno}: duplicate dependency {package}")
        seen[package] = lineno


def check_makefile(errors: list[str]) -> None:
    makefile = ROOT / "Makefile"
    if not makefile.is_file():
        fail(errors, "Makefile: missing")
        return
    text = makefile.read_text(encoding="utf-8")
    if "scaffold-skeleton:" not in text:
        fail(errors, "Makefile: missing scaffold-skeleton target")
    if "./aer-" in text:
        fail(errors, "Makefile: scaffold targets should require explicit DEST")
    for target in ("scaffold-stata", "scaffold-r", "scaffold-python", "scaffold-skeleton"):
        pattern = rf"{target}:\n\t@test -n \"\$\(DEST\)\""
        if not re.search(pattern, text):
            fail(errors, f"Makefile: {target} should require DEST")


def check_gitignore(errors: list[str]) -> None:
    gitignore = ROOT / ".gitignore"
    if not gitignore.is_file():
        fail(errors, ".gitignore: missing")
        return

    lines = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_patterns = (".claude/", "__pycache__/", ".venv/", "node_modules/")
    for pattern in required_patterns:
        if pattern not in lines:
            fail(errors, f".gitignore: missing {pattern}")


def check_no_tracked_generated_files(errors: list[str]) -> None:
    allowed = {
        "examples/replication-package-skeleton/logs/.gitkeep",
        "examples/replication-package-skeleton/output/figures/.gitkeep",
        "examples/replication-package-skeleton/output/tables/.gitkeep",
    }
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        fail(errors, f"git ls-files failed\n{result.stdout.strip()}")
        return

    for tracked in result.stdout.splitlines():
        if tracked in allowed:
            continue
        if any(part in GENERATED_OR_CACHE_DIRS for part in Path(tracked).parts):
            fail(errors, f"{tracked}: generated/cache path should not be tracked")


def check_ci_workflow(errors: list[str]) -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        fail(errors, f"{rel(workflow)}: missing")
        return
    text = workflow.read_text(encoding="utf-8")
    required_snippets = (
        "pull_request:",
        "branches:",
        "- main",
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "python-version: \"3.12\"",
        "sudo apt-get install -y r-base",
        "make validate-strict",
    )
    for snippet in required_snippets:
        if snippet not in text:
            fail(errors, f"{rel(workflow)}: missing {snippet!r}")


def check_no_local_paths(errors: list[str]) -> None:
    checked_roots = (
        ROOT / "templates",
        ROOT / "examples",
        ROOT / "scripts",
        ROOT / ".github",
    )
    checked_files = [ROOT / "Makefile"]
    for root in checked_roots:
        if root.exists():
            checked_files.extend(path for path in root.rglob("*") if path.is_file())

    for path in sorted(set(checked_files)):
        if any(part in GENERATED_OR_CACHE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in LOCAL_PATH_MARKERS:
            if marker in text:
                fail(errors, f"{rel(path)}: local absolute path marker {marker!r}")


def check_text_hygiene(errors: list[str]) -> None:
    for path in text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(errors, f"{rel(path)}: expected UTF-8 text")
            continue

        if text and not text.endswith("\n"):
            fail(errors, f"{rel(path)}: missing final newline")

        for lineno, line in enumerate(text.splitlines(), 1):
            if line.rstrip(" \t") != line:
                fail(errors, f"{rel(path)}:{lineno}: trailing whitespace")
                break


def check_placeholder_links(errors: list[str]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        if "journal site" in text.lower():
            fail(errors, f"{rel(path)}: replace 'journal site' placeholder with a DOI or stable URL")


def validate(require_optional_tools: bool = False) -> None:
    errors: list[str] = []
    check_validator_self_tests(errors)
    check_text_hygiene(errors)
    skill_names = check_skills(errors)
    check_plugin_manifest(skill_names, errors)
    check_skill_reference_docs(skill_names, errors)
    check_source_register(errors)
    check_policy_guardrails(errors)
    check_installation_guardrails(errors)
    check_skill_resource_links(errors)
    check_bibliography_integrity(errors)
    check_markdown_links(errors)
    check_template_layout(errors)
    check_example_demos(errors)
    check_python_templates(errors)
    check_cli_scripts(errors)
    check_r_templates(errors, require_optional_tools=require_optional_tools)
    check_stata_templates(errors)
    check_installer(errors)
    check_scaffolder(errors)
    check_requirements(errors)
    check_makefile(errors)
    check_gitignore(errors)
    check_no_tracked_generated_files(errors)
    check_ci_workflow(errors)
    check_no_local_paths(errors)
    check_placeholder_links(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise ValidationError(f"{len(errors)} validation error(s)")

    print("Repository validation passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-optional-tools",
        action="store_true",
        help="fail instead of warning when optional tools such as Rscript are unavailable",
    )
    args = parser.parse_args()

    try:
        validate(require_optional_tools=args.require_optional_tools)
    except ValidationError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
