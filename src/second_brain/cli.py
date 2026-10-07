"""Explicit command dispatch; commands retain their own arguments and gates."""
import argparse
import importlib
import sys

from .kb_common import TOOL_VERSION, run_cli

COMMANDS = {
    "init": "kb_init",
    "inventory": "kb_inventory",
    "packet": "kb_packet",
    "check": "kb_check",
    "reanchor": "kb_reanchor",
    "publish": "kb_publish",
    "mentions": "kb_mentions",
    "referrals": "kb_referrals",
    "index": "kb_index",
    "context": "kb_context",
    "run": "kb_run",
    "extract-document": "kb_extract_document",
    "visual-review": "kb_visual_review",
    "sync-skills": "kb_sync_skills",
    "reset-project": "kb_reset_project",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args()
    module = importlib.import_module("." + COMMANDS[args.command], __package__)
    original = sys.argv
    try:
        sys.argv = [f"second-brain {args.command}", *args.arguments]
        run_cli(module.main)
    finally:
        sys.argv = original
