# Privacy and AI processing

## Local data

Agentorium is a local desktop application. It does not operate a cloud service,
create user accounts, or include application telemetry. Story projects,
preferences, and AI task records are stored on the user's computer.

## What gets sent, and where

Agentorium never talks to a model provider itself. It invokes **the local
`claude` command** (Claude Code CLI) and hands the prompt to it. Where that
prompt is processed depends on how you configure the command — see
**Settings → AI engine**:

- **Leave the three fields blank (default).** The command uses its own login;
  credentials and the model endpoint are managed by your Claude Code
  installation, entirely outside this application.
- **Fill in endpoint / key / model.** The application passes them to the
  child process it starts. Requests then go to **the provider you named** —
  read that provider's terms and privacy policy before using AI features.

Depending on the action, the prompt may contain:

- the current chapter;
- outlines, the project writing-style guide, character profiles and
  world-building notes;
- chapter summaries and story state;
- the instruction needed to continue, review or summarize the story.

Do not submit personal data, confidential information, or copyrighted material
that you are not authorized to process. AI output may be inaccurate or
unsuitable and must be reviewed before use or publication.

## Credentials

If you fill in the **key** field, Agentorium stores it in the local
configuration file (`%APPDATA%\Agentorium\config.json` on Windows; see the
README for macOS and Linux paths). It is:

- used only to configure the child process this application starts;
- never written to logs, never sent anywhere except to the endpoint you named;
- never committed — the repository's `.gitignore` excludes local configuration.

Leave it blank and no credential is stored by this application at all.

Never commit `.env` files, API keys, tokens, personal `config.json` files, or
private writing projects.

## Network access

Agentorium makes no network requests of its own. The only outbound traffic is
what the local `claude` command does for an AI task you started, going to the
endpoint you configured (see "What gets sent, and where" above).
