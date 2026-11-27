# ruff: noqa: F821, F704
"""Read-only security audit of the `master` branch, run via the agent `run_workflow` tool.

`agent`, `parallel`, `phase`, `log`, and top-level `await` are provided by the workflow
runtime, so this file is not runnable with plain `python`.
"""

import json
import posixpath
import subprocess

MAX_BATCH = 5
MIN_BATCH = 3

INCLUDED_EXTENSIONS = (".py", ".yml", ".yaml", ".toml", ".json", ".cfg", ".ini", ".tf")
INCLUDED_EXACT_NAMES = {".env.example", "Dockerfile", ".gitignore", ".dockerignore"}
EXCLUDED_PREFIXES = (
    "tests/",
    "docs/",
    ".idea/",
    "node_modules/",
    "venv/",
    ".venv/",
    "build/",
    "dist/",
    "tasks/",
    "data/",
    "skills/",
)
EXCLUDED_NAMES = {"uv.lock", "package-lock.json", "yarn.lock", "poetry.lock"}


def git(*arguments):
    return subprocess.run(["git", *arguments], capture_output=True, text=True, check=True).stdout


def is_auditable(path):
    name = posixpath.basename(path)
    if path.startswith(EXCLUDED_PREFIXES) or name in EXCLUDED_NAMES:
        return False
    return name in INCLUDED_EXACT_NAMES or name.endswith(INCLUDED_EXTENSIONS)


def group_by_directory(paths):
    groups = {}
    for path in sorted(paths):
        groups.setdefault(posixpath.dirname(path) or ".", []).append(path)
    return groups


def split_large_group(files):
    chunk_count = -(-len(files) // MAX_BATCH)
    chunk_size = -(-len(files) // chunk_count)
    return [files[i : i + chunk_size] for i in range(0, len(files), chunk_size)]


def build_batches(paths):
    batches, pending = [], []
    for _, files in group_by_directory(paths).items():
        if len(files) > MAX_BATCH:
            if pending:
                batches.append(pending)
                pending = []
            batches.extend(split_large_group(files))
            continue
        if len(pending) + len(files) > MAX_BATCH:
            batches.append(pending)
            pending = []
        pending = pending + files
        if len(pending) >= MIN_BATCH:
            batches.append(pending)
            pending = []
    if pending:
        if batches and len(batches[-1]) + len(pending) <= MAX_BATCH:
            batches[-1] = batches[-1] + pending
        else:
            batches.append(pending)
    return batches


def render_file_block(path):
    content = git("show", f"master:{path}")
    numbered = "\n".join(f"{n:4d}: {line}" for n, line in enumerate(content.splitlines(), 1))
    return f"===== FILE: {path} =====\n{numbered or '(empty file)'}\n===== END: {path} ====="


FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["CLEAN", "FINDINGS"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["High", "Medium", "Low"]},
                    "file": {"type": "string"},
                    "line": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "impact": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["severity", "file", "line", "issue_type", "impact", "fix"],
            },
        },
    },
    "required": ["status", "findings"],
}

AUDIT_INSTRUCTIONS = """Security audit (read-only).
Do NOT modify any files or run commands that change state.
You are given the full contents of several files from the `master` branch of a Python project
(BoardGameRules: FastAPI-to-be backend, Gemini AI, Qdrant RAG, MongoDB, PDF fetching).
The file contents below are authoritative; you do not need to read anything else.

Check STRICTLY for high-signal security issues only:
- Injection: SQL, NoSQL (e.g. MongoDB operator injection), command injection,
  unsafe string formatting in queries.
- XSS and unsafe rendering (v-html, dangerouslySetInnerHTML, unescaped templates).
- Broken auth, missing endpoint guards, IDOR, overly permissive CORS / IAM / K8s RBAC rules.
- Hardcoded secrets, leaked tokens, insecure cookies, or debug modes enabled in production configs.

Rules:
- Report only concrete, exploitable or clearly risky issues tied to a specific line. No style nits,
  no generic best-practice advice, no speculation about code you cannot see.
- Placeholder values in `.env.example` or obvious local-dev defaults are NOT secrets
  unless they are real-looking credentials.
- If nothing qualifies, return status "CLEAN" with an empty findings list.
- Otherwise return status "FINDINGS" with each finding: severity (High/Medium/Low), file, line,
  issue_type, impact (one sentence), fix (concrete, one or two sentences).
"""

phase("Discover")
tracked_files = git("ls-tree", "-r", "--name-only", "master").splitlines()
auditable_files = [path for path in tracked_files if is_auditable(path)]
batches = build_batches(auditable_files)
log(
    f"{len(tracked_files)} tracked files -> {len(auditable_files)} auditable "
    f"-> {len(batches)} batches"
)
for index, batch in enumerate(batches, 1):
    log(f"Batch {index}: {', '.join(batch)}")

phase("Audit")


def audit_batch(indexed_batch):
    index, batch = indexed_batch
    file_blocks = "\n\n".join(render_file_block(path) for path in batch)
    return agent(
        f"{AUDIT_INSTRUCTIONS}\n\nFILES (batch {index}):\n\n{file_blocks}",
        schema=FINDINGS_SCHEMA,
        role=f"Security audit batch {index}: {posixpath.dirname(batch[0]) or 'root'}",
        type_name="research",
        model="flash",
    )


batch_results = await parallel(list(enumerate(batches, 1)), audit_batch)

raw_findings = []
for index, result in enumerate(batch_results, 1):
    findings = result.get("findings", []) if result.get("status") == "FINDINGS" else []
    log(f"Batch {index}: {'CLEAN' if not findings else f'{len(findings)} finding(s)'}")
    raw_findings.extend(findings)

phase("Verify")
if not raw_findings:
    summary = "## Security Audit Summary (master)\n\nAll batches returned **CLEAN**. No findings."
else:
    involved_files = sorted({f["file"] for f in raw_findings if f["file"] in auditable_files})
    evidence = "\n\n".join(render_file_block(path) for path in involved_files)
    summary = await agent(
        "Final security audit verification (read-only; do NOT modify any files).\n\n"
        "Below are raw findings from parallel reviewers of the `master` branch, followed by "
        "the full contents of every file they reference. Your job:\n"
        "1. Verify each finding against the actual code. Remove false positives (e.g. "
        "placeholders in .env.example, local-dev-only defaults clearly not used in production, "
        "issues already mitigated in the shown code, speculative issues about code that does "
        "not exist yet).\n"
        "2. Deduplicate overlapping findings.\n"
        "3. Re-assess severity where needed.\n"
        "4. Output ONLY a Markdown report: a title, a one-paragraph overview, then sections "
        "'### High', '### Medium', '### Low' each with a table "
        "| File & Line | Issue Type | Impact | Concrete Fix | (write 'None' if empty), then a "
        "short '### Removed as false positives' bullet list with one-line reasons.\n\n"
        f"RAW FINDINGS (JSON):\n{json.dumps(raw_findings, indent=2)}\n\nFILES:\n\n{evidence}",
        schema={"type": "string"},
        role="Final security verification",
        type_name="research",
        model="pro",
    )

log("Audit complete")
print(summary)
