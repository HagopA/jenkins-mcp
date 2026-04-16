import json
import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from mcp.server.fastmcp import FastMCP

load_dotenv()

_USER = os.environ["JENKINS_USER"]

# ---------------------------------------------------------------------------
# Instance registry
# Add or remove entries here to match your Jenkins infrastructure.
# Each key becomes the value you pass as ``instance_name`` in tool calls.
# ---------------------------------------------------------------------------

INSTANCES = {
    "integration": {
        "url": os.environ.get("JENKINS_URL_INTEGRATION", "https://jenkins-integration.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_INTEGRATION"],
    },
    "staging": {
        "url": os.environ.get("JENKINS_URL_STAGING", "https://jenkins-staging.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_STAGING"],
    },
    "teams": {
        "url": os.environ.get("JENKINS_URL_TEAMS", "https://jenkins-teams.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_TEAMS"],
    },
    "k8s_pipeline": {
        "url": os.environ.get("JENKINS_URL_K8S_PIPELINE", "https://jenkins-k8s-pipeline.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_K8S_PIPELINE"],
    },
    "ci": {
        "url": os.environ.get("JENKINS_URL_CI", "https://jenkins-ci.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_CI"],
    },
    "production": {
        "url": os.environ.get("JENKINS_URL_PRODUCTION", "https://jenkins-production.example.com"),
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_PRODUCTION"],
    },
}

mcp = FastMCP("jenkins")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def get_auth(instance: dict) -> HTTPBasicAuth:
    return HTTPBasicAuth(instance["user"], instance["token"])


def jenkins_get(instance: dict, path: str) -> dict:
    """Perform an authenticated GET against the Jenkins JSON API."""
    r = requests.get(
        f"{instance['url']}{path}",
        auth=get_auth(instance),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _resolve_targets(instance_name: str | None) -> dict:
    """Return a {name: config} dict for the requested instance(s).

    If *instance_name* is provided and valid, returns only that instance.
    If omitted or None, returns all configured instances (fan-out behaviour).
    """
    if instance_name and instance_name in INSTANCES:
        return {instance_name: INSTANCES[instance_name]}
    return INSTANCES


# ---------------------------------------------------------------------------
# Tool: get_job_parameters
# ---------------------------------------------------------------------------

@mcp.tool()
def get_job_parameters(job_name: str, instance_name: str = None) -> list:
    """Get the parameter definitions for a job on a Jenkins instance.

    Args:
        job_name: The Jenkins job name (e.g. ``MyPipeline`` or ``folder/MyJob``).
        instance_name: Target a specific instance by name (see INSTANCES keys).
                       If omitted, all instances are queried.

    Returns:
        List of ``{"instance": str, "parameters": [...]}`` entries for each
        instance where the job exists.
    """
    targets = _resolve_targets(instance_name)
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                f"/job/{job_name}/api/json"
                "?tree=property[parameterDefinitions[name,type,defaultParameterValue[value],description]]",
            )
            param_defs = []
            for prop in data.get("property", []):
                if "parameterDefinitions" in prop:
                    param_defs = prop["parameterDefinitions"]
                    break
            if param_defs:
                results.append({"instance": name, "parameters": param_defs})
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                results.append({"instance": name, "error": str(e)})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Tool: trigger_build_on_all
# ---------------------------------------------------------------------------

@mcp.tool()
def trigger_build_on_all(
    job_name: str,
    instance_name: str = None,
    parameters: str = None,
) -> list:
    """Trigger a build for a job on one or all Jenkins instances.

    Args:
        job_name: The Jenkins job name.
        instance_name: Target a specific instance. If omitted, triggers on all.
        parameters: Optional JSON string of build parameters,
                    e.g. ``'{"BRANCH": "main", "RUN_TESTS": "true"}'``.

    Returns:
        List of ``{"instance": str, "status": str}`` entries.
    """
    targets = _resolve_targets(instance_name)
    params = json.loads(parameters) if parameters else None
    results = []
    for name, instance in targets.items():
        try:
            if params:
                r = requests.post(
                    f"{instance['url']}/job/{job_name}/buildWithParameters",
                    auth=get_auth(instance),
                    params=params,
                    timeout=10,
                )
            else:
                r = requests.post(
                    f"{instance['url']}/job/{job_name}/build",
                    auth=get_auth(instance),
                    timeout=10,
                )
            if r.status_code == 404:
                continue
            if r.status_code in (200, 201):
                results.append({"instance": name, "status": f"Build triggered for {job_name}"})
            else:
                results.append({"instance": name, "status": f"Failed: {r.status_code}"})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Tool: get_build_history_from_all
# ---------------------------------------------------------------------------

@mcp.tool()
def get_build_history_from_all(job_name: str, instance_name: str = None) -> list:
    """Get recent build history for a job, including who triggered each build.

    Queries the last 20 builds and flattens the ``causes`` action so the
    triggering user is surfaced at the top level of each build entry.

    Args:
        job_name: The Jenkins job name.
        instance_name: Target a specific instance. If omitted, queries all.

    Returns:
        List of ``{"instance": str, "builds": [...]}`` entries.
    """
    targets = _resolve_targets(instance_name)
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                f"/job/{job_name}/api/json"
                "?tree=builds[number,result,timestamp,duration,building,"
                "actions[causes[userId,userName]]]{0,20}",
            )
            builds = data.get("builds", [])
            if builds:
                simplified = []
                for b in builds:
                    causes = [
                        cause
                        for action in b.get("actions", [])
                        for cause in action.get("causes", [])
                        if "userId" in cause
                    ]
                    simplified.append(
                        {
                            "number": b["number"],
                            "result": b.get("result"),
                            "building": b.get("building"),
                            "duration": b.get("duration"),
                            "timestamp": b.get("timestamp"),
                            "triggered_by": causes,
                        }
                    )
                results.append({"instance": name, "builds": simplified})
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                results.append({"instance": name, "error": str(e)})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Tool: get_failure_log
# ---------------------------------------------------------------------------

@mcp.tool()
def get_failure_log(
    job_name: str,
    instance_name: str,
    build_number: str = "lastBuild",
    tail_lines: int = 50,
) -> dict:
    """Fetch the tail of the console log for a build — ideal for diagnosing failures.

    Waits until the build is complete before returning (returns a ``"still running"``
    message if the build has not finished yet).

    Args:
        job_name: The Jenkins job name.
        instance_name: The target Jenkins instance (required).
        build_number: Build number or ``"lastBuild"`` (default).
        tail_lines: Number of lines from the end of the log to return (default 50).

    Returns:
        Dict with ``instance``, ``build_number``, ``result``, and ``log_tail``.
    """
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}. Available: {list(INSTANCES)}"}
    instance = INSTANCES[instance_name]
    try:
        data = jenkins_get(instance, f"/job/{job_name}/{build_number}/api/json")
        if data.get("building"):
            return {"instance": instance_name, "status": "Build is still running"}
        r = requests.get(
            f"{instance['url']}/job/{job_name}/{build_number}/consoleText",
            auth=get_auth(instance),
            timeout=10,
        )
        r.raise_for_status()
        lines = r.text.splitlines()
        return {
            "instance": instance_name,
            "build_number": build_number,
            "result": data.get("result"),
            "log_tail": "\n".join(lines[-tail_lines:]),
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: search_build_log
# ---------------------------------------------------------------------------

@mcp.tool()
def search_build_log(
    job_name: str,
    instance_name: str,
    keyword: str,
    build_number: str = "lastBuild",
) -> dict:
    """Search for a keyword in a build's console log.

    Returns up to 20 matching lines, each with 2 lines of surrounding context
    for readability.

    Args:
        job_name: The Jenkins job name.
        instance_name: The target Jenkins instance (required).
        keyword: Case-insensitive search term.
        build_number: Build number or ``"lastBuild"`` (default).

    Returns:
        Dict with ``match_count`` and a ``matches`` list of
        ``{"line": int, "context": str}`` entries.
    """
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}. Available: {list(INSTANCES)}"}
    instance = INSTANCES[instance_name]
    try:
        r = requests.get(
            f"{instance['url']}/job/{job_name}/{build_number}/consoleText",
            auth=get_auth(instance),
            timeout=10,
        )
        r.raise_for_status()
        lines = r.text.splitlines()
        matches = []
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 3)
                matches.append(
                    {
                        "line": i + 1,
                        "context": "\n".join(lines[context_start:context_end]),
                    }
                )
        return {
            "instance": instance_name,
            "build_number": build_number,
            "keyword": keyword,
            "match_count": len(matches),
            "matches": matches[:20],
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: list_artifacts
# ---------------------------------------------------------------------------

@mcp.tool()
def list_artifacts(
    job_name: str,
    instance_name: str,
    build_number: str = "lastBuild",
) -> dict:
    """List all artifacts available for a build.

    Args:
        job_name: The Jenkins job name.
        instance_name: The target Jenkins instance (required).
        build_number: Build number or ``"lastBuild"`` (default).

    Returns:
        Dict with ``artifacts`` list of ``{"fileName": str, "relativePath": str}``.
    """
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}. Available: {list(INSTANCES)}"}
    instance = INSTANCES[instance_name]
    try:
        data = jenkins_get(
            instance,
            f"/job/{job_name}/{build_number}/api/json?tree=artifacts[fileName,relativePath]",
        )
        return {
            "instance": instance_name,
            "build_number": build_number,
            "artifacts": data.get("artifacts", []),
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_artifact_content
# ---------------------------------------------------------------------------

@mcp.tool()
def get_artifact_content(
    job_name: str,
    instance_name: str,
    artifact_path: str,
    build_number: str = "lastBuild",
    tail_lines: int = 100,
) -> dict:
    """Download and tail a build artifact file.

    Call ``list_artifacts`` first to discover available ``artifact_path`` values.

    Args:
        job_name: The Jenkins job name.
        instance_name: The target Jenkins instance (required).
        artifact_path: Relative path of the artifact (from ``list_artifacts``).
        build_number: Build number or ``"lastBuild"`` (default).
        tail_lines: Number of lines from the end of the file to return (default 100).

    Returns:
        Dict with ``total_lines``, ``returned_lines``, and ``content``.
    """
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}. Available: {list(INSTANCES)}"}
    instance = INSTANCES[instance_name]
    try:
        r = requests.get(
            f"{instance['url']}/job/{job_name}/{build_number}/artifact/{artifact_path}",
            auth=get_auth(instance),
            timeout=15,
        )
        r.raise_for_status()
        lines = r.text.splitlines()
        tail = lines[-tail_lines:]
        return {
            "instance": instance_name,
            "build_number": build_number,
            "artifact_path": artifact_path,
            "total_lines": len(lines),
            "returned_lines": len(tail),
            "content": "\n".join(tail),
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: search_artifact_content
# ---------------------------------------------------------------------------

@mcp.tool()
def search_artifact_content(
    job_name: str,
    instance_name: str,
    artifact_path: str,
    keyword: str,
    build_number: str = "lastBuild",
) -> dict:
    """Search for a keyword inside a build artifact file.

    Returns up to 20 matching lines with surrounding context.

    Args:
        job_name: The Jenkins job name.
        instance_name: The target Jenkins instance (required).
        artifact_path: Relative path of the artifact (from ``list_artifacts``).
        keyword: Case-insensitive search term.
        build_number: Build number or ``"lastBuild"`` (default).

    Returns:
        Dict with ``match_count`` and a ``matches`` list of
        ``{"line": int, "context": str}`` entries.
    """
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}. Available: {list(INSTANCES)}"}
    instance = INSTANCES[instance_name]
    try:
        r = requests.get(
            f"{instance['url']}/job/{job_name}/{build_number}/artifact/{artifact_path}",
            auth=get_auth(instance),
            timeout=15,
        )
        r.raise_for_status()
        lines = r.text.splitlines()
        matches = []
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 3)
                matches.append(
                    {
                        "line": i + 1,
                        "context": "\n".join(lines[context_start:context_end]),
                    }
                )
        return {
            "instance": instance_name,
            "build_number": build_number,
            "artifact_path": artifact_path,
            "keyword": keyword,
            "total_lines": len(lines),
            "match_count": len(matches),
            "matches": matches[:20],
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
