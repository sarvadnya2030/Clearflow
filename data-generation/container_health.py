#!/usr/bin/env python3
"""Real, read-only container health tool -- closes the exact blind spot that
bit this project twice this session: logstash OOM-killed 21 hours unnoticed,
Neo4j OOM-killed 4 days unnoticed. The existing health-witness monitor only
sees APPLICATION-level health (/actuator/health on the 8 Java services);
nothing before this could answer "did the infra itself silently die."

Uses `docker inspect` (read-only, no state-changing docker commands) against
the real container for a named infra component.
"""
import json
import subprocess

# logical component name -> real docker container name
COMPONENT_CONTAINERS = {
    "logstash": "infrastructure-logstash-1",
    "elasticsearch": "infrastructure-elasticsearch-1",
    "kafka": "infrastructure-kafka-1",
    "zookeeper": "infrastructure-zookeeper-1",
    "redis": "infrastructure-redis-1",
    "mongodb": "infrastructure-mongodb-1",
    "cassandra": "infrastructure-cassandra-1",
    "activemq-artemis": "infrastructure-activemq-artemis-1",
    "neo4j": "infrastructure-neo4j-1",
    "mcp-readonly-gateway": "infrastructure-mcp-readonly-gateway-1",
}


def get_container_health(component):
    """Real docker inspect against one named infra component. Returns
    status, exit code (if exited), how long it's been in that state, and
    restart count -- the actual host-level truth /actuator/health can't see
    for infra a Java service depends on but doesn't embed."""
    container = COMPONENT_CONTAINERS.get(component)
    if not container:
        return {"error": f"unknown component '{component}', known: {list(COMPONENT_CONTAINERS)}"}
    try:
        out = subprocess.run(
            ["docker", "inspect", container], capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return {"component": component, "container": container,
                    "status": "NOT_FOUND", "detail": out.stderr.strip()[:300]}
        data = json.loads(out.stdout)[0]
        state = data.get("State", {})
        return {
            "component": component,
            "container": container,
            "status": state.get("Status"),
            "running": state.get("Running"),
            "exit_code": state.get("ExitCode"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "restart_count": data.get("RestartCount"),
            "oom_killed": state.get("OOMKilled"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_all_infra_health():
    """Check every known infra component at once -- what an agent should
    call FIRST, before assuming any application-level symptom is the whole
    story."""
    return {name: get_container_health(name) for name in COMPONENT_CONTAINERS}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(get_container_health(sys.argv[1]), indent=2))
    else:
        for name, health in get_all_infra_health().items():
            flag = "OK" if health.get("running") else f"DOWN ({health.get('status')}, exit={health.get('exit_code')}, oom={health.get('oom_killed')})"
            print(f"{name:25s} {flag}")
