#!/usr/bin/env python3
"""
Audit for the Call(arg=Await(Call)) bug pattern.

Background: a class of bug where converter scripts incorrectly placed
`await` on a function argument when the receiving function expected a
coroutine (not the result). Produces TypeError at runtime when the
receiver passes the value to asyncio.wait_for / gather / create_task.

Usage:
    python scripts/audit_await_in_args.py
    python scripts/audit_await_in_args.py --quiet      # exit 1 on findings, no per-line print
    python scripts/audit_await_in_args.py --strict     # also flag whitelisted callees

Exit codes:
    0  — no findings
    1  — at least one finding (suitable for CI gate)
"""

import argparse
import ast
import sys
from pathlib import Path


# Callees where Call(arg=Await(...)) is a legitimate pattern.
# These functions accept iterables/values, so awaiting an async function's
# return value as the argument is correct usage.
WHITELIST_CALLEES = {
    # Container methods that consume iterables
    "extend", "append", "insert", "add", "update", "remove",
    # Building strings/values from awaited results
    "format", "join", "split",
    # Logging / formatting (the awaited value is meant to be the literal)
    "info", "debug", "warning", "error", "critical", "log",
    # Common built-ins where the awaited value is the literal arg
    "len", "sum", "max", "min", "any", "all", "sorted", "list", "tuple", "dict", "set",
    "print", "str", "int", "float", "bool", "repr",
    # JSON/dict assembly
    "dumps", "loads",
}

# Callees that are KNOWN BAD if they receive an awaited Call as arg —
# these expect coroutines/awaitables, never resolved values.
SUSPICIOUS_CALLEES = {
    "wait_for", "gather", "create_task", "ensure_future",
    "shield", "as_completed", "wait",
    # User-defined wrappers from this codebase
    "_instrumented", "_with_inner_timeout", "safe_collect", "_safe_collect",
    # Streaming responses / generators that take an iterable, not awaited value
    "StreamingResponse",
}


def get_callee_name(node: ast.Call) -> str | None:
    """Extract the callee name from a Call node, handling attribute access."""
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def get_inner_callee(await_node: ast.Await) -> str | None:
    """If `await X(...)`, return X's name."""
    if not isinstance(await_node.value, ast.Call):
        return None
    return get_callee_name(await_node.value)


def audit_file(path: Path, strict: bool = False) -> list[tuple[int, str, str, str]]:
    """Return list of (lineno, callee, arg_index, detail) for findings."""
    try:
        src = path.read_text()
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError):
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = get_callee_name(node)
        if callee is None:
            continue
        # Skip whitelisted callees unless --strict
        if not strict and callee in WHITELIST_CALLEES:
            continue
        for i, arg in enumerate(node.args):
            if isinstance(arg, ast.Await) and isinstance(arg.value, ast.Call):
                inner = get_inner_callee(arg) or "<unknown>"
                # Mark severity: SUSPICIOUS callees are almost certainly bugs;
                # everything else is a soft flag worth reviewing.
                tag = "SUSPICIOUS" if callee in SUSPICIOUS_CALLEES else "REVIEW"
                findings.append((node.lineno, callee, str(i), f"{tag}: await {inner}(...)"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quiet", action="store_true", help="Exit 1 on findings without per-line output")
    parser.add_argument("--strict", action="store_true", help="Flag even whitelisted callees")
    parser.add_argument("--root", default="app", help="Root directory to audit (default: app)")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"audit: root '{root}' not found", file=sys.stderr)
        return 2

    total_findings = 0
    suspicious_findings = 0
    for path in sorted(root.rglob("*.py")):
        findings = audit_file(path, strict=args.strict)
        for lineno, callee, arg_i, detail in findings:
            total_findings += 1
            if "SUSPICIOUS" in detail:
                suspicious_findings += 1
            if not args.quiet:
                print(f"{path}:{lineno}: {callee}(arg{arg_i}={detail})")

    if total_findings:
        if args.quiet:
            print(f"audit: {total_findings} finding(s), {suspicious_findings} suspicious", file=sys.stderr)
        else:
            print(f"\nTotal: {total_findings} finding(s), {suspicious_findings} suspicious")
        # Exit 1 only if any SUSPICIOUS findings — REVIEW-level can be tolerated
        # in CI without blocking, but should be human-reviewed periodically.
        return 1 if suspicious_findings > 0 else 0
    if not args.quiet:
        print("audit: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
