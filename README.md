# Jenkins MCP Server for Claude Code

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects
Claude Code directly to Jenkins CI/CD. Once registered, Claude can fetch logs, diagnose
build failures, trigger jobs, and inspect artifacts conversationally — without leaving
the editor.

Claude Code auto-starts the server in the background — you never need to start it manually.

## Tools

| Tool | Description |
|---|---|
| `get_job_parameters` | Retrieve parameter definitions for a job |
| `trigger_build_on_all` | Trigger a build with optional parameters |
| `get_build_history_from_all` | Recent build history, including who triggered each build |
| `get_failure_log` | Tail a build's console log (default: last 50 lines) |
| `search_build_log` | Search a console log for a keyword with surrounding context |
| `list_artifacts` | List all artifacts attached to a build |
| `get_artifact_content` | Download and tail a build artifact file |
| `search_artifact_content` | Search for a keyword inside a build artifact |

## How It Works

```
Claude Code ──(MCP stdio)──► jenkins_mcp.py ──(HTTPS + API token)──► Jenkins REST API
```

1. Claude issues a tool call over stdio (the MCP transport).
2. `jenkins_mcp.py` translates it into one or more Jenkins JSON API requests authenticated
   with `HTTPBasicAuth`.
3. Results are returned as structured data that Claude reasons over directly.

### Multi-instance support

The server maintains a named registry of Jenkins instances. Every tool accepts an optional
`instance_name` parameter:

- **Provided** — targets that instance only.
- **Omitted** — fans out across all configured instances simultaneously.

This lets a single MCP registration serve an organization with multiple Jenkins servers
(e.g. per-team or per-release-stream instances).

---

## Setup

### Prerequisites

- Python 3.10+
- [Claude Code](https://claude.ai/claude-code) CLI
- A Jenkins API token for each instance — generate one at:
  **Jenkins → your user → Configure → API Token**

### 1. Create a virtual environment

Run this once from the folder where `jenkins_mcp.py` lives:

```bash
python -m venv .venv
```

Activate it:

```bash
# Mac / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

> **Windows:** If you see a "running scripts is disabled on this system" error, run this
> once first, then activate:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

### 2. Install dependencies

With the venv active:

```bash
pip install mcp requests python-dotenv
```

### 3. Create your `.env` file

In the same folder as `jenkins_mcp.py`, create a file named `.env`. **Keep this file
private — never share or commit it.**

```env
JENKINS_USER=your.name@example.com

JENKINS_TOKEN_INTEGRATION=your_api_token_here
JENKINS_TOKEN_STAGING=your_api_token_here
JENKINS_TOKEN_TEAMS=your_api_token_here
JENKINS_TOKEN_K8S_PIPELINE=your_api_token_here
JENKINS_TOKEN_CI=your_api_token_here
JENKINS_TOKEN_PRODUCTION=your_api_token_here
```

The server reads credentials from `.env` automatically via `python-dotenv`. No secrets
live in the code.

### 4. Configure `CLAUDE.md`

Claude Code reads `~/.claude/CLAUDE.md` at session start for behavioral instructions.
Add the following block to configure how Claude interacts with Jenkins:

```markdown
## Jenkins

If no Jenkins instance has been established in the conversation, ask the user which
instance they mean before making any tool calls. Present the available options:

- integration
- staging
- teams
- k8s_pipeline
- ci
- production

Once an instance is established in the conversation, continue using it for subsequent
tool calls unless told otherwise.

When the user asks why a specific job is failing, call `get_failure_log` directly.
If the log identifies a failing subjob, automatically call `get_failure_log` on that
subjob too — keep following the chain until the root cause is found. Do not ask for
permission at each step.
```

### 5. Register with Claude Code

Run this once. Replace the paths with the actual locations of your `.venv` and
`jenkins_mcp.py`:

```bash
# Mac / Linux
claude mcp add --scope user jenkins -- /path/to/jenkins/.venv/bin/python /path/to/jenkins/jenkins_mcp.py

# Windows
claude mcp add --scope user jenkins -- C:\path\to\jenkins\.venv\Scripts\python.exe C:\path\to\jenkins\jenkins_mcp.py
```

That's it. Claude Code will automatically start the server at the beginning of every
session using the venv's Python — no manual startup needed.

---

## Tools Reference

Some tools are designed to be called by Claude internally as part of a reasoning chain,
rather than invoked via a specific prompt. For example, asking *"Why did this build fail?"*
will cause Claude to call `get_failure_log`, follow any failing subjobs, and if the console
log is too high-level, automatically chain into `list_artifacts` → `search_artifact_content`
to find the root cause — all without you needing to name the tools.

The descriptions below are useful when you want to target a specific tool directly (e.g.,
"List the artifacts for build 2466").

### Triggering

#### `trigger_build_on_all`

Trigger a build for a job on a specific instance. Claude calls `get_job_parameters` first
to present available parameters before triggering.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `parameters` | No | JSON string of build parameters, e.g. `{"PARAM1": "value1"}` |

#### `get_job_parameters`

Get a job's parameter definitions. Claude calls this automatically before triggering a
parameterized build.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |

### History

#### `get_build_history_from_all`

Recent build history (last 20) for a job, including who triggered each build.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |

### Log Inspection

#### `get_failure_log`

Get the tail of the console log for a completed build. Claude uses this automatically
when diagnosing failures and chains through failing subjobs to find the root cause.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `build_number` | No | Defaults to `lastBuild` |
| `tail_lines` | No | Defaults to `50` |

#### `search_build_log`

Search for a keyword in a build's console log. Returns matching lines with 2 lines of
surrounding context (up to 20 matches).

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `keyword` | Yes | Search term (case-insensitive) |
| `build_number` | No | Defaults to `lastBuild` |

### Artifacts

#### `list_artifacts`

List all artifacts available for a build.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `build_number` | No | Defaults to `lastBuild` |

#### `get_artifact_content`

Get the tail of a build artifact file. Use `list_artifacts` first to find the artifact
path. Defaults to last 100 lines to avoid large payloads.

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `artifact_path` | Yes | Relative artifact path (from `list_artifacts`) |
| `build_number` | No | Defaults to `lastBuild` |
| `tail_lines` | No | Defaults to `100` |

#### `search_artifact_content`

Search for a keyword in a build artifact file. Returns matching lines with surrounding
context (up to 20 matches).

| Parameter | Required | Description |
|---|---|---|
| `job_name` | Yes | Exact job name |
| `instance_name` | Yes | Instance name |
| `artifact_path` | Yes | Relative artifact path (from `list_artifacts`) |
| `keyword` | Yes | Search term (case-insensitive) |
| `build_number` | No | Defaults to `lastBuild` |

---

## Notes

- **Credentials:** Stored in `.env` alongside `jenkins_mcp.py`. Keep this file private —
  never share or commit it.
- **Auto-start:** Once registered, Claude Code spawns the server automatically at session
  start using the venv Python you specified. You never need to activate the venv or start
  the server manually.
- **Folder support:** Jobs inside Jenkins folders are found automatically — you never need
  to type a folder path. If a keyword matches multiple jobs across folders or instances,
  Claude will list them and ask which one you meant.
