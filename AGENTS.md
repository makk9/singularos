# AGENTS.md

Rules for AI coding agents (Claude Code, Codex, Copilot, Gemini, opencode, etc.) working in this repository.

This repository is **public**. Everything committed here, including history, commit messages, and PR text, is visible to anyone and stays in git history even after deletion. Treat every write as publishing.

## What belongs in the repo

- Source code, tests, and build/config files for the project.
- Documentation of the project: what it is, how to install, run, test, and contribute.
- Example configuration with placeholder values only (e.g. `.env.example` with `API_KEY=your-key-here`).
- Small, license-compatible assets the project needs to build or run.
- Third-party code only if its license is compatible with MIT and its license/attribution is preserved.

## What does not belong in the repo

- **Secrets of any kind:** API keys, tokens, passwords, private keys, SSH keys, certificates, cookies, session files, `.env` files, OAuth client secrets, connection strings with credentials. If one is committed by mistake, stop and tell a maintainer: it must be rotated, not just deleted.
- **Personal or identifying information:** home directory paths (e.g. `/Users/<name>/...`, `C:\Users\<name>\...`), email addresses, phone numbers, physical addresses, internal hostnames, private IP addresses, device names, account IDs.
- **Machine- or contributor-specific configuration:** editor settings, local agent settings (e.g. `.claude/settings.local.json`), absolute paths, local tool versions pinned to one machine.
- **Content from private sources:** private repos, internal documents, chat logs, emails, meeting notes, or agent session transcripts.
- **Generated or bulky artifacts:** build output, `node_modules/`, virtualenvs, caches, logs, model weights, datasets, large binaries. Add these to `.gitignore` instead.
- **Agent scratch work:** plans, TODO dumps, analysis notes, or debugging transcripts that are not project documentation.
- **Commentary:** files and commit messages state facts only (what something is, how to run it, what changed). No editorial asides, opinions, self-assessment of agent work, or notes about which model or tool produced a change.
- Code or text copied from sources whose license is unknown or incompatible with MIT.

## Before committing

1. Review the full diff (`git diff --staged`), not just the files you meant to change.
2. Search staged changes for secrets and personal data: keys, tokens, `password`, `secret`, email addresses, absolute home paths, private IPs.
3. Confirm no ignored or generated files are staged.
4. Write a commit message that describes the change factually.

## When unsure

If you are not certain whether something is safe to publish, do not commit it. Leave it out and ask a maintainer.
