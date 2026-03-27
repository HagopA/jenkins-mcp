# jenkins-mcp

An MCP (Model Context Protocol) server that exposes Jenkins CI/CD operations as tools, allowing AI assistants like Claude to interact with one or more Jenkins instances directly.

## Features

- Search jobs across all instances, including nested folders
- List all jobs and their statuses
- Trigger builds with or without parameters
- Cancel builds individually or by user
- Get build logs, failure tails, and console search
- View build history and success rates
- Monitor running builds and queue status
- Resolve queue items to build numbers

## Requirements

- Python 3.10+
- One or more Jenkins instances with API access
- A Jenkins API token per instance

## Installation

```bash
git clone https://github.com/HagopA/jenkins-mcp.git
cd jenkins-mcp

python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install mcp requests python-dotenv
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
JENKINS_USER=your.name@example.com
JENKINS_TOKEN_INTEGRATION=your_api_token_here
JENKINS_TOKEN_STAGING=your_api_token_here
JENKINS_TOKEN_TEAMS=your_api_token_here
JENKINS_TOKEN_K8S_PIPELINE=your_api_token_here
JENKINS_TOKEN_CI=your_api_token_here
JENKINS_TOKEN_PRODUCTION=your_api_token_here
```

Then update the `INSTANCES` dictionary in `jenkins_mcp.py` with your Jenkins URLs and corresponding environment variable names:

```python
INSTANCES = {
    "my-instance": {
        "url": "https://jenkins.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_MY_INSTANCE"],
    },
    # add more instances as needed
}
```

## Usage with Claude

Register the server with Claude using the `claude mcp add` command, pointing to the venv's Python interpreter so dependencies are available:

```bash
# macOS / Linux
claude mcp add jenkins /absolute/path/to/.venv/bin/python /absolute/path/to/jenkins_mcp.py

# Windows
claude mcp add jenkins /absolute/path/to/.venv/Scripts/python /absolute/path/to/jenkins_mcp.py
```

Once added, Claude will automatically start the MCP server on each new session — no manual config editing required.

## Available Tools

| Tool | Description |
|------|-------------|
| `list_all_jobs` | List all jobs across all instances |
| `search_all_jobs` | Search jobs by keyword, including inside folders |
| `get_job_status_from_all` | Get the last build status of a job across all instances |
| `get_job_parameters` | Get parameter definitions for a job |
| `trigger_build_on_all` | Trigger a build, optionally on a specific instance with parameters |
| `get_build_number_from_queue` | Resolve a queue URL to an actual build number |
| `cancel_build` | Cancel/abort a specific build |
| `cancel_builds_by_user` | Cancel all running builds triggered by a user |
| `get_build_log_from_all` | Get the console log of a specific build |
| `get_failure_log` | Get the tail of a build log (useful for diagnosing failures) |
| `search_build_log` | Search for a keyword in a build log with context |
| `get_build_history_from_all` | Get recent build history including who triggered each build |
| `get_running_builds` | Get all currently running builds |
| `get_queue_status` | Get all items currently waiting in the queue |
| `get_build_success_rate` | Get success/failure/abort rates over the last N builds |
| `search_builds_by_user` | Find recent builds triggered by a specific user |
