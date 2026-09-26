# Transcripts

Auto-recorded prompts and responses (see `.claude/hooks/transcript.py`).

---

## 2026-09-26 19:42:16 — session `current0`

**User:**

Make a rule that records all our prompts/conversations. Add this into a Transcripts.md file to record our conversations

**Claude:**

Every prompt you send and every reply I give will now be appended to `Transcripts.md` in the project root. I tested the script with sample input and it wrote a correct prompt/reply entry. I haven't seen it run in a real session yet.

**How it works:**
- **The script** is `.claude/hooks/transcript.py`. It uses `python3`, because `jq` isn't installed here.
- **When you send a prompt**, it adds a timestamped heading with the session ID, followed by your prompt.
- **When I finish a reply**, it adds my text from that turn. Tool calls and their output are left out.
- **The trigger** is in `.claude/settings.json`, as hooks on the events "you send a prompt" and "I finish a reply". This file is meant to be committed, so the logging comes with the repo.
- **If logging fails**, the error is ignored so it never blocks the conversation.

**Two things to know:**
1. **This session probably isn't being logged yet.** The `.claude/` folder didn't exist when this session started, so Claude Code likely hasn't loaded the new settings. Open `/hooks` once or restart Claude Code to turn it on. I added your prompt from this conversation to `Transcripts.md` by hand, with a made-up session ID (`current0`). My reply to it will only be recorded if the logging is already on.
2. **Everything in the conversation gets saved**, including anything sensitive you paste. The file isn't gitignored, so it will be committed with everything else. If you'd rather keep it local, add `Transcripts.md` to `.gitignore`.

You can review or turn off the logging anytime with `/hooks`.
