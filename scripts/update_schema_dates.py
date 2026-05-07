#!/usr/bin/env python3
"""Update TechArticleSchema dateModified (and datePublished for new files).

Designed to run in CI on PRs touching .mdx files. Logic:
  - For each ADDED .mdx file: set both datePublished and dateModified to today.
  - For each MODIFIED .mdx file: bump dateModified to today, but only if the
    PR diff touches lines OUTSIDE the <TechArticleSchema /> block. Diffs that
    only touch the schema block itself (e.g., automated date bumps) are
    skipped — this is what prevents a workflow loop.
  - Files that don't have a TechArticleSchema component are left alone.

Usage: python scripts/update_schema_dates.py <base_ref>
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

SCHEMA_BLOCK_RE = re.compile(r"<TechArticleSchema\s.*?/>", re.DOTALL)
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def changed_mdx_files(base_ref: str) -> tuple[list[str], list[str]]:
    """Return (added, modified) lists of .mdx file paths in this PR."""
    added = run(
        "git", "diff", "--name-only", "--diff-filter=A",
        f"origin/{base_ref}...HEAD"
    ).splitlines()
    modified = run(
        "git", "diff", "--name-only", "--diff-filter=M",
        f"origin/{base_ref}...HEAD"
    ).splitlines()
    return (
        [f for f in added if f.endswith(".mdx")],
        [f for f in modified if f.endswith(".mdx")],
    )


def schema_line_range(content: str) -> tuple[int, int] | None:
    """Return (start, end) 1-based line numbers of the schema block, or None."""
    match = SCHEMA_BLOCK_RE.search(content)
    if not match:
        return None
    start = content[: match.start()].count("\n") + 1
    end = content[: match.end()].count("\n") + 1
    return (start, end)


def diff_touches_non_schema(filepath: str, base_ref: str, schema_range: tuple[int, int]) -> bool:
    """True if any diff hunk in this PR touches a line outside the schema block."""
    diff = run("git", "diff", f"origin/{base_ref}...HEAD", "--unified=0", "--", filepath)
    schema_start, schema_end = schema_range
    for line in diff.splitlines():
        m = HUNK_HEADER_RE.match(line)
        if not m:
            continue
        new_start = int(m.group(1))
        new_count = int(m.group(2)) if m.group(2) is not None else 1
        if new_count == 0:
            # Pure deletion: the position is where the change "happens" in new file
            if new_start < schema_start or new_start > schema_end:
                return True
            continue
        new_end = new_start + new_count - 1
        # Hunk overlaps non-schema lines if it starts before or ends after the schema range
        if new_start < schema_start or new_end > schema_end:
            return True
    return False


def update_dates_in_file(filepath: str, set_published: bool) -> bool:
    """Rewrite dateModified (and optionally datePublished) to today. Returns True if changed."""
    path = Path(filepath)
    if not path.exists():
        return False
    content = path.read_text()

    new_content = re.sub(
        r'(\sdateModified=)"[^"]*"',
        rf'\1"{TODAY}"',
        content,
        count=1,
    )
    if set_published:
        new_content = re.sub(
            r'(\sdatePublished=)"[^"]*"',
            rf'\1"{TODAY}"',
            new_content,
            count=1,
        )

    if new_content == content:
        return False
    path.write_text(new_content)
    return True


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: update_schema_dates.py <base_ref>", file=sys.stderr)
        sys.exit(2)
    base_ref = sys.argv[1]

    added, modified = changed_mdx_files(base_ref)
    updated: list[str] = []
    skipped_schema_only: list[str] = []
    skipped_no_schema: list[str] = []

    for f in added:
        if update_dates_in_file(f, set_published=True):
            updated.append(f"{f} (new)")

    for f in modified:
        path = Path(f)
        if not path.exists():
            continue  # deleted in this PR
        content = path.read_text()
        schema_range = schema_line_range(content)
        if schema_range is None:
            skipped_no_schema.append(f)
            continue
        if not diff_touches_non_schema(f, base_ref, schema_range):
            skipped_schema_only.append(f)
            continue
        if update_dates_in_file(f, set_published=False):
            updated.append(f)

    print(f"Updated: {len(updated)}")
    for f in updated:
        print(f"  - {f}")
    if skipped_schema_only:
        print(f"Skipped (schema-only diff): {len(skipped_schema_only)}")
    if skipped_no_schema:
        print(f"Skipped (no schema in file): {len(skipped_no_schema)}")


if __name__ == "__main__":
    main()
