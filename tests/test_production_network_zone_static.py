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


def test_video_zone_override_is_explicit_dmz_only_extension():
    base_compose = Path("docker-compose.production.yml").read_text()
    video_zone_override = Path("docker-compose.production.video-zones.yml").read_text()

    assert "PRIMARY_DMZ_VIDEO_IP" not in base_compose
    assert "BACKUP_DMZ_VIDEO_IP" not in base_compose
    assert "PRIMARY_DMZ_VIDEO_IP" in video_zone_override
    assert "BACKUP_DMZ_VIDEO_IP" in video_zone_override
    assert "PRIMARY_DMZ_PORT_RANGE" in video_zone_override
    assert "BACKUP_DMZ_PORT_RANGE" in video_zone_override
    assert "api:" not in video_zone_override
    assert "grafana:" not in video_zone_override
    assert "redis:" not in video_zone_override
    assert "db:" not in video_zone_override


def test_single_server_env_splits_backup_ports_when_dmz_ip_is_shared():
    env_path = ".env.production.single-server.example"

    assert _env_value(env_path, "PRIMARY_PORT_RANGE") == "9000-9010"
    assert _env_value(env_path, "BACKUP_PORT_RANGE") == "9011-9021"
    assert _env_value(env_path, "PRIMARY_DMZ_PORT_RANGE") == "9000-9010"
    assert _env_value(env_path, "BACKUP_DMZ_PORT_RANGE") == "9011-9021"
    assert _env_value(env_path, "PRIMARY_DMZ_VIDEO_IP") == "10.75.51.40"
    assert _env_value(env_path, "BACKUP_DMZ_VIDEO_IP") == "10.75.51.40"


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


def test_docs_show_video_zone_override_as_optional_compose_file():
    readme = Path("README.md").read_text()
    guide = Path("UI_USER_GUIDE.md").read_text()
    context = Path(".agent-context.md").read_text()

    assert "-f docker-compose.production.yml -f docker-compose.production.video-zones.yml" in readme
    assert "Docker UDP publishing is controlled separately" in readme
    assert "docker-compose.production.video-zones.yml" in context
    assert "Docker UDP port publishing" in guide
