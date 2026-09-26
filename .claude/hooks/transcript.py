#!/usr/bin/env python3
"""Append user prompts and Claude's replies to Transcripts.md.

Wired up in .claude/settings.json:
  UserPromptSubmit -> logs the prompt
  Stop             -> logs Claude's final text for the turn
"""
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
TRANSCRIPT_MD = os.path.join(PROJECT_DIR, "Transcripts.md")
HEADER = "# Transcripts\n\nAuto-recorded prompts and responses (see `.claude/hooks/transcript.py`).\n"


def last_turn_text(transcript_path):
    """Collect assistant text blocks written since the most recent user prompt."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return ""
    chunks = []
    for entry in reversed(entries):
        msg = entry.get("message") or {}
        if entry.get("type") == "user" and isinstance(msg.get("content"), str):
            break  # reached the prompt that started this turn
        if entry.get("type") == "assistant":
            for block in reversed(msg.get("content") or []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    chunks.append(block["text"].strip())
    return "\n\n".join(reversed(chunks))


def append(section):
    new_file = not os.path.exists(TRANSCRIPT_MD)
    with open(TRANSCRIPT_MD, "a", encoding="utf-8") as f:
        if new_file:
            f.write(HEADER)
        f.write(section)


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = (data.get("session_id") or "")[:8]

    if event == "UserPromptSubmit":
        prompt = (data.get("prompt") or "").strip()
        if prompt:
            append(f"\n---\n\n## {stamp} — session `{session}`\n\n**User:**\n\n{prompt}\n")
    elif event == "Stop":
        text = data.get("last_assistant_message") or last_turn_text(data.get("transcript_path", ""))
        if text:
            append(f"\n**Claude:**\n\n{text.strip()}\n")


if __name__ == "__main__":
    main()
