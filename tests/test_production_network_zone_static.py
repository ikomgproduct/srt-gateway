import json
from pathlib import Path


PRODUCTION_ENV_FILES = [
    ".env.production.single-server.example",
    ".env.production.control-plane.example",
    ".env.production.primary.example",
    ".env.production.backup.example",
]


def _env_value(path: str, key: str) -> str:
    for line in Path(path).read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"{key} is missing from {path}")


def test_video_zone_override_is_valid_noop_compatibility_file():
    base_compose = Path("docker-compose.production.yml").read_text()
    video_zone_override = Path("docker-compose.production.video-zones.yml").read_text()

    assert "PRIMARY_DMZ_VIDEO_IP" not in base_compose
    assert "BACKUP_DMZ_VIDEO_IP" not in base_compose
    assert "services: {}" in video_zone_override
    assert "Compatibility-only" in video_zone_override
    assert "api:" not in video_zone_override
    assert "grafana:" not in video_zone_override
    assert "redis:" not in video_zone_override
    assert "db:" not in video_zone_override


def test_production_workers_use_host_network_without_deprecated_ranges():
    env_path = ".env.production.single-server.example"
    compose = Path("docker-compose.production.yml").read_text()

    assert compose.count("network_mode: host") == 2
    assert "PRIMARY_PORT_RANGE" not in Path(env_path).read_text()
    assert "BACKUP_PORT_RANGE" not in Path(env_path).read_text()
    assert _env_value(env_path, "UDP_MULTICAST_PORT_MIN") == "1024"
    assert _env_value(env_path, "UDP_MULTICAST_PORT_MAX") == "65535"
    assert _env_value(env_path, "REDIS_BIND_IP") == "127.0.0.1"


def test_runtime_dependencies_include_greenlet_for_async_sqlalchemy():
    requirements = {
        line.split("==", 1)[0].strip().lower()
        for line in Path("requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "greenlet" in requirements or "sqlalchemy[asyncio]" in requirements


def test_production_env_interface_inventory_contains_four_zones():
    required_zones = {"main-video", "backup-video", "dmz-video", "management"}

    for env_path in PRODUCTION_ENV_FILES:
        inventory = json.loads(_env_value(env_path, "INTERFACE_INVENTORY_JSON"))
        zones = {item["zone"] for item in inventory}
        assert required_zones.issubset(zones), env_path


def test_production_env_management_inventory_is_not_media_selectable():
    for env_path in PRODUCTION_ENV_FILES:
        inventory = json.loads(_env_value(env_path, "INTERFACE_INVENTORY_JSON"))
        management = next(item for item in inventory if item["zone"] == "management")
        assert management["purpose"] == "management"
        assert management["network"] == "management"
        assert management["directions"] == []
        assert management["node_roles"] == []


def test_production_redis_and_worker_connectivity_are_scoped():
    compose = Path("docker-compose.production.yml").read_text()

    assert "REDIS_PASSWORD=${REDIS_PASSWORD:?REDIS_PASSWORD is required}" in compose
    assert '"${REDIS_BIND_IP:-127.0.0.1}:${REDIS_PORT:-6379}:6379"' in compose
    assert compose.count("WORKER_REDIS_URL=${WORKER_REDIS_URL:?WORKER_REDIS_URL is required}") == 2
    assert _env_value(".env.production.single-server.example", "REDIS_BIND_IP") == "127.0.0.1"
    assert _env_value(".env.production.control-plane.example", "REDIS_BIND_IP") == "10.75.15.3"
    assert "10.75.51.40:6379" not in compose


def test_production_grafana_password_is_required_for_every_profile_env():
    compose = Path("docker-compose.production.yml").read_text()

    assert "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}" in compose
    assert "GRAFANA_ADMIN_PASSWORD:-admin" not in compose
    for env_path in PRODUCTION_ENV_FILES:
        assert _env_value(env_path, "GRAFANA_ADMIN_PASSWORD") == "change-me"


def test_docs_show_host_network_and_compatibility_override():
    readme = Path("README.md").read_text()
    guide = Path("UI_USER_GUIDE.md").read_text()
    context = Path(".agent-context.md").read_text()

    assert "Production workers use Linux host networking" in readme
    assert "empty compatibility file" in readme
    assert "docker-compose.production.video-zones.yml" in context
    assert "not required for a new installation" in readme
    assert "one-release compatibility override" in readme
    assert "Do not add interface addresses, port ranges, or services" in readme
    assert ".env.production.single-server.local" in readme
    assert "Compose no longer publishes a fixed media-port window" in guide
    assert "PRIMARY_VIDEO_IP=" not in readme
    assert "BACKUP_VIDEO_IP=" not in readme
    assert "published host/container port window" not in readme


def test_server_local_production_env_files_are_not_committed_or_built():
    assert ".env.production.*.local" in Path(".gitignore").read_text()
    assert ".env.production.*.local" in Path(".dockerignore").read_text()


def test_docs_align_current_dmz_bind_contract_with_env_examples():
    readme = Path("README.md").read_text()
    context = Path(".agent-context.md").read_text()
    architecture = Path("docs/architecture.md").read_text()
    product_brief = Path("docs/product-brief.md").read_text()

    assert "API_BIND_IP=10.75.51.40" in Path(".env.production.single-server.example").read_text()
    assert "GRAFANA_ALT_BIND_IP=10.75.51.40" in Path(".env.production.single-server.example").read_text()
    assert "API/UI is directly DMZ-accessible on `10.75.51.40:8000`" in readme
    assert "Redis/Postgres must not be exposed to DMZ" in readme
    assert "Current production supports direct explicit DMZ/management binds" in context
    assert "direct DMZ binds may remain for current operations" in architecture
    assert "Current production supports direct explicit UI/Grafana binds" in product_brief
    assert "API/UI and Grafana should bind only to management IPs" not in context
    assert "management-bound API/Grafana" not in readme
