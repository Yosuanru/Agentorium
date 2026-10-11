# Agentorium

> A local-first AI workspace for long-form novel writing.

Agentorium helps individual authors and small creative teams keep a long story coherent over dozens or hundreds of chapters. It brings manuscripts, outlines, character sheets, worldbuilding, timelines, chapter summaries, story state, and plot threads into one local desktop workspace.

## What It Solves

Writing one chapter with AI is easy. Keeping characters, world rules, timelines, and foreshadowing consistent over a long project is much harder. A single conversation gradually loses context, and a model reviewing its own writing may miss its own mistakes.

Agentorium addresses these problems with:

- Local project files that remain portable and inspectable
- AI-assisted text expansion
- Consistency inspection against characters, world rules, systems, and timelines
- Persistent chapter summaries, character state, and foreshadowing
- Structured result validation before AI output is written back
- Replaceable AI backends and explicit human approval

Agentorium is not a one-click system for generating an entire novel. It is the workspace around a deliberate writing process: agents read and write project files, while the author reviews evidence, chooses revisions, and keeps final control of the story.

## The Multi-Agent Workflow

The wider workflow uses four specialized roles:

| Role | Access | Responsibility |
|---|---|---|
| **Writer** | Manuscript, canon, outline, and memory | Drafts or revises chapters |
| **Cold Reader** | Manuscript only | Reports where a first-time reader gets lost or disengaged |
| **Permanent Reader** | New or changed chapters and its own notes | Checks continuity and whether revisions improved the reading experience |
| **Logic Reviewer** | Manuscript, canon, outline, and memory | Finds factual, timeline, causal, and setting conflicts |

Information is intentionally isolated. Reader feedback is cross-checked before revision, and the Logic Reviewer can work independently before seeing other reviewers' opinions. The multi-agent pipeline is currently coordinated manually by the author, leaving creative judgment where it belongs: with the human author.

## Screenshots

### Project overview

![Project overview](assets/screenshots/01-overview-dark.png)

### Story canon

![Story canon](assets/screenshots/02-canon-dark.png)

### Consistency report

![Consistency report](assets/screenshots/03-report-dark.png)

### Light theme

![Light theme](assets/screenshots/04-overview-light.png)

### AI settings

![AI settings](assets/screenshots/05-settings-ai.png)

## Run Locally

### Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux
- Optional: Claude Code CLI for the full local-agent workflow

### Install and start

```bash
pip install -r requirements.txt
python main.py
```

On Windows, you can also double-click `run.bat`, or use:

```powershell
py main.py
```

The application stores projects as ordinary folders containing Markdown and JSON files. A project can be copied, inspected, versioned, or moved without a proprietary database.

## AI Backends

Agentorium supports two backends from **Settings → AI Engine**.

### Anthropic-compatible API

Enter an endpoint, API key, and model name. For example:

```text
Endpoint: https://api.deepseek.com/anthropic
Model:    deepseek-v4-flash
```

Any provider that exposes a compatible Messages API can be used. The key is stored in the user's local application configuration and is not written to the repository.

### Local Claude Code CLI

Install the CLI if needed:

```bash
npm install --global @anthropic-ai/claude-code
```

The CLI backend supports the full agent workflow, including reading and writing project files. Leaving the API fields empty preserves the CLI's normal authentication behavior.

Before an AI result is saved, Agentorium validates its chapter ID, source-text anchors, permitted field range, and structured protocol format. Task snapshots and stale-result protection prevent an old task from silently overwriting newer work. File updates use atomic writes.

## Technology

- Python 3.10+
- PySide6 desktop GUI
- Markdown and JSON local storage
- Python standard-library `urllib`
- Anthropic-compatible Messages API
- Claude Code CLI integration
- Structured AI output protocols and context budgeting
- Task snapshots, stale-result protection, and atomic writes
- PyInstaller Windows packaging

DeepSeek V4.1 Flash was used during development for code generation, refactoring suggestions, and debugging assistance. Project direction, requirements, feature decisions, integration, testing, documentation, and releases were handled by the project author.

## Project Structure

```text
main.py                 Application entry point
core/                   Project, storage, AI, memory, and validation logic
ui/                     Desktop interface and workflow views
assets/                 Icons, fonts, and screenshots
projects/               Example and user projects
tests/                  Automated tests
DESIGN.md               Multi-agent workflow and information boundaries
FILES.md                File-by-file project map
PRIVACY.md              Data handling and local storage notes
```

## Blockchain Status

Not applicable. The current version does not use blockchain. Manuscripts, settings, memories, and task data are stored locally. AI requests are sent only to model services configured by the user. Agentorium does not simulate on-chain features or write private creative content to a public ledger.

## Origin and License

Agentorium is based on the open-source project [Novalist](https://github.com/xiauho/novalist). The upstream project and this derivative work follow the MIT License. See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md), and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and dependency notices.

## Author

Agentorium is built by an undergraduate Cyberspace Security student at Henan Normal University. The project is developed for authors who want the leverage of AI without giving up local data control or final creative judgment.
