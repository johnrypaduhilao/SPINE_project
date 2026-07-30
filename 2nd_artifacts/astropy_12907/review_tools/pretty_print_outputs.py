"""
pretty_print_outputs.py

Turn the raw JSON files in outputs/ into something a human can actually read.

The raw files are valid JSON but unreadable: every diff, issue body and test
list is squashed onto one line as a single string full of \\n escapes, and a
few fields (FAIL_TO_PASS, PASS_TO_PASS) are JSON *inside* a JSON string.

This script never modifies an original file. For each source file it writes
new companion files next to it:

  <name>.pretty.json    valid JSON, indented, embedded JSON strings expanded
                        into real arrays/objects, and every multi-line string
                        split into an array of lines so no \\n or \\r escapes
                        survive anywhere in the file
  <name>.readable.txt   plain text report where multi-line fields are printed
                        as real lines, blank-line separated, indented

JSON cannot hold a literal newline inside a string, so a field like `patch`
can only be one escaped line -- unless it stops being one string. Splitting it
into ["diff --git ...", "--- a/...", ...] keeps the file valid JSON while
putting one real source line on each row. Pass --raw-strings to keep the
original single-string shape instead.

Run (PowerShell uses python, Git Bash uses py):
  python pretty_print_outputs.py                    process outputs/
  python pretty_print_outputs.py some/dir           process another directory
  python pretty_print_outputs.py --format text      only the .txt report
  python pretty_print_outputs.py --format json      only the .pretty.json
  python pretty_print_outputs.py --raw-strings      keep \\n escapes in the JSON
  python pretty_print_outputs.py --indent 4         wider JSON indentation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Files this script itself generates, so re-running never processes its own
# output and never recurses.
GENERATED_SUFFIXES = (".pretty.json", ".readable.txt")

TEXT_WIDTH = 78


def expand_embedded_json(value):
    """Recursively parse strings that are themselves JSON documents.

    SWE-bench stores FAIL_TO_PASS / PASS_TO_PASS as a JSON array encoded
    inside a string. Left alone they print as one long escaped line; parsed
    they become real arrays that indent one item per line.
    """
    if isinstance(value, dict):
        return {key: expand_embedded_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_embedded_json(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                return value
            if isinstance(parsed, (dict, list)):
                return expand_embedded_json(parsed)
        return value
    return value


def split_multiline_strings(value):
    """Turn every multi-line string into an array of its lines.

    A JSON string physically cannot contain a newline, so `patch` and
    `problem_statement` are stuck on one escaped line for as long as they stay
    single strings. As a list of lines they are still valid JSON, but each
    source line lands on its own row and no \\n or \\r escape remains.
    """
    if isinstance(value, dict):
        return {key: split_multiline_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [split_multiline_strings(item) for item in value]
    if isinstance(value, str):
        text = normalize_newlines(value)
        if "\n" not in text:
            return text
        lines = text.split("\n")
        # A trailing newline would otherwise leave a pointless "" last element.
        if lines and lines[-1] == "":
            lines.pop()
        return lines
    return value


def normalize_newlines(text: str) -> str:
    """Collapse CRLF / CR to LF so the text report has no stray blank lines."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def indent_block(text: str, pad: str) -> str:
    """Indent every line of a block, leaving blank lines truly blank."""
    lines = normalize_newlines(text).split("\n")
    return "\n".join(pad + line if line.strip() else "" for line in lines)


def render_value(value, depth: int, out: list) -> None:
    """Append a human-readable rendering of one value to `out`."""
    pad = "  " * depth

    if isinstance(value, dict):
        if not value:
            out.append(pad + "(empty)")
            return
        for key, item in value.items():
            render_field(key, item, depth, out)
        return

    if isinstance(value, list):
        if not value:
            out.append(pad + "(empty list)")
            return
        for index, item in enumerate(value, start=1):
            if isinstance(item, (dict, list)):
                out.append("%s%d." % (pad, index))
                render_value(item, depth + 1, out)
                out.append("")
            else:
                out.append("%s%3d. %s" % (pad, index, scalar_text(item)))
        return

    out.append(indent_block(scalar_text(value), pad))


def scalar_text(value) -> str:
    if value is None:
        return "(null)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value if value.strip() else "(empty)"
    return str(value)


def render_field(key: str, value, depth: int, out: list) -> None:
    """Render one `key: value` pair, choosing inline vs. block layout."""
    pad = "  " * depth

    # Short single-line scalar: keep it on the same line as the key.
    if not isinstance(value, (dict, list)):
        text = scalar_text(value)
        if "\n" not in normalize_newlines(text) and len(text) <= TEXT_WIDTH:
            out.append("%s%s: %s" % (pad, key, text))
            out.append("")
            return

    if isinstance(value, list):
        out.append("%s%s  (%d item%s)" % (pad, key, len(value),
                                          "" if len(value) == 1 else "s"))
    else:
        out.append("%s%s:" % (pad, key))
    out.append("")
    render_value(value, depth + 1, out)
    out.append("")


def build_text_report(data, title: str) -> str:
    out: list = []
    rule = "=" * TEXT_WIDTH
    out.append(rule)
    out.append(title)
    out.append(rule)
    out.append("")
    render_value(data, 0, out)

    # Collapse runs of blank lines down to one, and end with a single newline.
    cleaned: list = []
    for line in out:
        if not line.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(line.rstrip())
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned) + "\n"


def process_file(src: Path, indent: int, want_json: bool, want_text: bool,
                 raw_strings: bool = False) -> list:
    """Write the requested companion files for one source file."""
    data = json.loads(src.read_text(encoding="utf-8"))
    expanded = expand_embedded_json(data)
    written = []

    if want_json:
        payload = expanded if raw_strings else split_multiline_strings(expanded)
        dest = src.with_name(src.stem + ".pretty.json")
        dest.write_text(
            json.dumps(payload, indent=indent, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(dest)

    if want_text:
        dest = src.with_name(src.stem + ".readable.txt")
        dest.write_text(build_text_report(expanded, src.name), encoding="utf-8")
        written.append(dest)

    return written


def is_generated(path: Path) -> bool:
    return any(path.name.endswith(suffix) for suffix in GENERATED_SUFFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write human-readable copies of JSON files. Originals are "
                    "never modified."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default="outputs",
        help="Directory containing JSON files (default: outputs).",
    )
    parser.add_argument(
        "--format",
        choices=("both", "json", "text"),
        default="both",
        help="Which companion files to write (default: both).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Spaces of indentation for the .pretty.json (default: 2).",
    )
    parser.add_argument(
        "--raw-strings",
        action="store_true",
        help="Keep multi-line fields as single escaped strings in the "
             "pretty JSON instead of splitting them into arrays of lines.",
    )
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        print("Error: %s is not a valid directory." % root)
        return 1

    sources = sorted(p for p in root.rglob("*.json") if not is_generated(p))
    if not sources:
        print("No source JSON files found in: %s" % root)
        return 0

    want_json = args.format in ("both", "json")
    want_text = args.format in ("both", "text")
    failures = 0

    for src in sources:
        try:
            for dest in process_file(src, args.indent, want_json, want_text,
                                     raw_strings=args.raw_strings):
                print("Created: %s" % dest)
        except json.JSONDecodeError as error:
            failures += 1
            print("Skipped invalid JSON: %s (%s)" % (src, error))
        except Exception as error:
            failures += 1
            print("Error processing %s: %s" % (src, error))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
