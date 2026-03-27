import json
import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from mcp.server.fastmcp import FastMCP

load_dotenv()

_USER = os.environ["JENKINS_USER"]

INSTANCES = {
    "integration": {
        "url": "https://jenkins-integration.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_INTEGRATION"],
    },
    "staging": {
        "url": "https://jenkins-staging.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_STAGING"],
    },
    "teams": {
        "url": "https://jenkins-teams.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_TEAMS"],
    },
    "k8s-pipeline": {
        "url": "https://jenkins-k8s-pipeline.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_K8S_PIPELINE"],
    },
    "ci": {
        "url": "https://jenkins-ci.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_CI"],
    },
    "production": {
        "url": "https://jenkins-production.example.com",
        "user": _USER,
        "token": os.environ["JENKINS_TOKEN_PRODUCTION"],
    },
}

mcp = FastMCP("jenkins")


def get_auth(instance: dict) -> HTTPBasicAuth:
    return HTTPBasicAuth(instance["user"], instance["token"])


def jenkins_get(instance: dict, path: str) -> dict:
    r = requests.get(
        f"{instance['url']}{path}",
        auth=get_auth(instance),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


@mcp.tool()
def search_all_jobs(keyword: str) -> list:
    """Search for jobs matching a keyword across all Jenkins instances, including jobs inside folders"""
    def collect_jobs(instance, path="/", job_path_prefix=""):
        try:
            url_path = f"{path}api/json?tree=jobs[name,url,color,jobs[name,url,color,jobs[name,url,color]]]"
            data = jenkins_get(instance, url_path)
            found = []
            for job in data.get("jobs", []):
                job_path = f"{job_path_prefix}{job['name']}" if not job_path_prefix else f"{job_path_prefix}/job/{job['name']}"
                if keyword.lower() in job["name"].lower():
                    found.append({**job, "job_path": job_path})
                if job.get("jobs") is not None:
                    for subjob in job.get("jobs", []):
                        subjob_path = f"{job_path}/job/{subjob['name']}"
                        if keyword.lower() in subjob["name"].lower():
                            found.append({**subjob, "job_path": subjob_path})
                        if subjob.get("jobs") is not None:
                            for subsubjob in subjob.get("jobs", []):
                                subsubjob_path = f"{subjob_path}/job/{subsubjob['name']}"
                                if keyword.lower() in subsubjob["name"].lower():
                                    found.append({**subsubjob, "job_path": subsubjob_path})
            return found
        except Exception as e:
            return [{"error": str(e)}]

    results = []
    for name, instance in INSTANCES.items():
        try:
            matches = collect_jobs(instance)
            for m in matches:
                results.append({**m, "instance": name})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_job_status_from_all(job_name: str) -> list:
    """Find and return the status of a job across all Jenkins instances"""
    results = []
    for name, instance in INSTANCES.items():
        try:
            data = jenkins_get(instance, f"/job/{job_name}/lastBuild/api/json")
            results.append({"instance": name, **data})
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                results.append({"instance": name, "error": str(e)})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def list_all_jobs() -> list:
    """List all jobs from all Jenkins instances"""
    results = []
    for name, instance in INSTANCES.items():
        try:
            data = jenkins_get(instance, "/api/json?tree=jobs[name,url,color]")
            for job in data.get("jobs", []):
                results.append({**job, "instance": name})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_build_log_from_all(job_name: str, build_number: int) -> list:
    """Get the console log of a specific build across all Jenkins instances"""
    results = []
    for name, instance in INSTANCES.items():
        try:
            r = requests.get(
                f"{instance['url']}/job/{job_name}/{build_number}/consoleText",
                auth=get_auth(instance),
                timeout=10,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            results.append({"instance": name, "log": r.text[:5000]})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_job_parameters(job_name: str) -> list:
    """Get the parameter definitions for a job across all Jenkins instances where it exists"""
    results = []
    for name, instance in INSTANCES.items():
        try:
            data = jenkins_get(
                instance,
                f"/job/{job_name}/api/json?tree=property[parameterDefinitions[name,type,defaultParameterValue[value],description]]"
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


@mcp.tool()
def trigger_build_on_all(job_name: str, instance_name: str = None, parameters: str = None) -> list:
    """Trigger a build for a job. Optionally target a specific instance and/or pass parameters as a JSON string, e.g. '{"PARAM1": "value1"}'"""
    targets = {instance_name: INSTANCES[instance_name]} if instance_name and instance_name in INSTANCES else INSTANCES
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
                queue_url = r.headers.get("Location", "")
                results.append({
                    "instance": name,
                    "status": f"Build triggered for {job_name}",
                    "queue_url": queue_url,
                    "note": "Use get_build_number_from_queue to resolve the actual build number before cancelling."
                })
            else:
                results.append({"instance": name, "status": f"Failed: {r.status_code}"})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_build_number_from_queue(instance_name: str, queue_url: str) -> dict:
    """Resolve a queue item URL to an actual build number. Call this after trigger_build_on_all to get the specific build number before cancelling."""
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}"}
    instance = INSTANCES[instance_name]
    try:
        # Extract queue item path from full URL
        path = queue_url.replace(instance["url"], "").rstrip("/")
        r = requests.get(
            f"{instance['url']}{path}/api/json",
            auth=get_auth(instance),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        executable = data.get("executable")
        if executable:
            return {
                "instance": instance_name,
                "build_number": executable["number"],
                "build_url": executable["url"],
            }
        return {"instance": instance_name, "status": "Build not started yet — still in queue. Try again in a moment."}
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


@mcp.tool()
def cancel_build(job_name: str, instance_name: str, build_number: str = "lastBuild") -> dict:
    """Cancel/abort a running build. Defaults to the last build if no build number is provided."""
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}"}
    instance = INSTANCES[instance_name]
    try:
        r = requests.post(
            f"{instance['url']}/job/{job_name}/{build_number}/stop",
            auth=get_auth(instance),
            timeout=10,
        )
        if r.status_code in (200, 201, 302):
            return {"instance": instance_name, "status": f"Build {build_number} cancelled for {job_name}"}
        return {"instance": instance_name, "status": f"Failed: {r.status_code}"}
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


@mcp.tool()
def get_build_history_from_all(job_name: str) -> list:
    """Get recent build history for a job across all Jenkins instances, including who triggered each build"""
    results = []
    for name, instance in INSTANCES.items():
        try:
            data = jenkins_get(
                instance,
                f"/job/{job_name}/api/json?tree=builds[number,result,timestamp,duration,building,actions[causes[userId,userName]]]{{0,20}}"
            )
            builds = data.get("builds", [])
            if builds:
                # Flatten causes into each build for easier reading
                simplified = []
                for b in builds:
                    causes = []
                    for action in b.get("actions", []):
                        for cause in action.get("causes", []):
                            if "userId" in cause:
                                causes.append(cause)
                    simplified.append({
                        "number": b["number"],
                        "result": b.get("result"),
                        "building": b.get("building"),
                        "duration": b.get("duration"),
                        "timestamp": b.get("timestamp"),
                        "triggered_by": causes,
                    })
                results.append({"instance": name, "builds": simplified})
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                results.append({"instance": name, "error": str(e)})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def cancel_builds_by_user(job_name: str, instance_name: str, username: str = _USER, limit: int = None) -> list:
    """Cancel running builds triggered by a specific user. Use limit to cancel only the last N builds, or omit to cancel all running builds by that user."""
    if instance_name not in INSTANCES:
        return [{"error": f"Unknown instance: {instance_name}"}]
    instance = INSTANCES[instance_name]
    results = []
    try:
        data = jenkins_get(
            instance,
            f"/job/{job_name}/api/json?tree=builds[number,result,building,actions[causes[userId]]]{{0,100}}"
        )
        builds = data.get("builds", [])

        # Filter to running builds triggered by the specified user
        matching = []
        for b in builds:
            if not b.get("building"):
                continue
            for action in b.get("actions", []):
                for cause in action.get("causes", []):
                    if cause.get("userId", "").lower() == username.lower():
                        matching.append(b["number"])
                        break

        if limit:
            matching = matching[:limit]

        if not matching:
            return [{"instance": instance_name, "status": f"No running builds found for user '{username}' in {job_name}"}]

        for build_number in matching:
            r = requests.post(
                f"{instance['url']}/job/{job_name}/{build_number}/stop",
                auth=get_auth(instance),
                timeout=10,
            )
            if r.status_code in (200, 201, 302):
                results.append({"instance": instance_name, "build": build_number, "status": "Cancelled"})
            else:
                results.append({"instance": instance_name, "build": build_number, "status": f"Failed: {r.status_code}"})
    except Exception as e:
        results.append({"instance": instance_name, "error": str(e)})
    return results


@mcp.tool()
def get_running_builds(instance_name: str = None) -> list:
    """Get all currently running builds across all (or a specific) Jenkins instance"""
    targets = {instance_name: INSTANCES[instance_name]} if instance_name and instance_name in INSTANCES else INSTANCES
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                "/api/json?tree=jobs[name,builds[number,building,timestamp,url,actions[causes[userId,userName]]]{0,5}]"
            )
            running = []
            for job in data.get("jobs", []):
                for build in job.get("builds", []):
                    if not build.get("building"):
                        continue
                    causes = []
                    for action in build.get("actions", []):
                        for cause in action.get("causes", []):
                            if "userId" in cause:
                                causes.append(cause)
                    running.append({
                        "job": job["name"],
                        "build_number": build["number"],
                        "triggered_by": causes,
                        "timestamp": build.get("timestamp"),
                        "url": build.get("url"),
                    })
            if running:
                results.append({"instance": name, "running_builds": running})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_failure_log(job_name: str, instance_name: str, build_number: str = "lastBuild", tail_lines: int = 50) -> dict:
    """Get the tail of the console log for a build. Useful for diagnosing failures. Defaults to the last build."""
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}"}
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


@mcp.tool()
def search_builds_by_user(username: str = _USER, instance_name: str = None, limit: int = 20) -> list:
    """Search recent builds triggered by a specific user across all (or a specific) Jenkins instance."""
    targets = {instance_name: INSTANCES[instance_name]} if instance_name and instance_name in INSTANCES else INSTANCES
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                "/api/json?tree=jobs[name,builds[number,result,building,timestamp,duration,actions[causes[userId,userName]]]{0,50}]"
            )
            matches = []
            for job in data.get("jobs", []):
                for build in job.get("builds", []):
                    for action in build.get("actions", []):
                        for cause in action.get("causes", []):
                            if cause.get("userId", "").lower() == username.lower():
                                matches.append({
                                    "job": job["name"],
                                    "build_number": build["number"],
                                    "result": build.get("result"),
                                    "building": build.get("building"),
                                    "timestamp": build.get("timestamp"),
                                    "duration": build.get("duration"),
                                })
                                break
            matches = matches[:limit]
            if matches:
                results.append({"instance": name, "builds": matches})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_queue_status(instance_name: str = None) -> list:
    """Get all items currently waiting in the Jenkins queue across all (or a specific) instance."""
    targets = {instance_name: INSTANCES[instance_name]} if instance_name and instance_name in INSTANCES else INSTANCES
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                "/queue/api/json?tree=items[id,why,blocked,stuck,task[name,url],actions[causes[userId,userName],parameters[name,value]]]"
            )
            items = data.get("items", [])
            queue_items = []
            for item in items:
                causes = []
                params = {}
                for action in item.get("actions", []):
                    for cause in action.get("causes", []):
                        if "userId" in cause:
                            causes.append(cause)
                    for p in action.get("parameters", []):
                        if "value" in p:
                            params[p["name"]] = p["value"]
                queue_items.append({
                    "id": item["id"],
                    "job": item.get("task", {}).get("name"),
                    "why": item.get("why"),
                    "blocked": item.get("blocked"),
                    "stuck": item.get("stuck"),
                    "triggered_by": causes,
                    "parameters": params,
                })
            results.append({"instance": name, "queue": queue_items})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def get_build_success_rate(job_name: str, instance_name: str = None, count: int = 20) -> list:
    """Get the success rate of a job over the last N builds."""
    targets = {instance_name: INSTANCES[instance_name]} if instance_name and instance_name in INSTANCES else INSTANCES
    results = []
    for name, instance in targets.items():
        try:
            data = jenkins_get(
                instance,
                f"/job/{job_name}/api/json?tree=builds[number,result]{{0,{count}}}"
            )
            builds = data.get("builds", [])
            if not builds:
                continue
            completed = [b for b in builds if b.get("result")]
            if not completed:
                continue
            success = sum(1 for b in completed if b["result"] == "SUCCESS")
            failure = sum(1 for b in completed if b["result"] == "FAILURE")
            aborted = sum(1 for b in completed if b["result"] == "ABORTED")
            rate = round((success / len(completed)) * 100, 1)
            results.append({
                "instance": name,
                "job": job_name,
                "builds_checked": len(completed),
                "success": success,
                "failure": failure,
                "aborted": aborted,
                "success_rate": f"{rate}%",
            })
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                results.append({"instance": name, "error": str(e)})
        except Exception as e:
            results.append({"instance": name, "error": str(e)})
    return results


@mcp.tool()
def search_build_log(job_name: str, instance_name: str, keyword: str, build_number: str = "lastBuild") -> dict:
    """Search for a keyword in a build's console log and return matching lines with surrounding context."""
    if instance_name not in INSTANCES:
        return {"error": f"Unknown instance: {instance_name}"}
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
                matches.append({
                    "line": i + 1,
                    "context": "\n".join(lines[context_start:context_end]),
                })
        return {
            "instance": instance_name,
            "build_number": build_number,
            "keyword": keyword,
            "match_count": len(matches),
            "matches": matches[:20],
        }
    except Exception as e:
        return {"instance": instance_name, "error": str(e)}


if __name__ == "__main__":
    mcp.run()
