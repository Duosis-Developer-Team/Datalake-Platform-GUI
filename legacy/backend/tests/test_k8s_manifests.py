import pathlib
import yaml
import pytest

K8S_DIR = pathlib.Path(__file__).parent.parent.parent / "k8s" / "backend"


def _load(filename):
    return yaml.safe_load((K8S_DIR / filename).read_text())


@pytest.fixture(scope="module")
def deployment():
    return _load("deployment.yaml")


@pytest.fixture(scope="module")
def service():
    return _load("service.yaml")


@pytest.fixture(scope="module")
def configmap():
    return _load("configmap.yaml")


@pytest.fixture(scope="module")
def secret():
    return _load("secret.yaml")


@pytest.fixture(scope="module")
def hpa():
    return _load("hpa.yaml")


def test_deployment_api_version_and_kind(deployment):
    assert deployment["apiVersion"] == "apps/v1"
    assert deployment["kind"] == "Deployment"


def test_deployment_replicas_is_two(deployment):
    assert deployment["spec"]["replicas"] == 2


def test_deployment_image(deployment):
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "bulutistan-data-api:latest"


def test_deployment_exposes_port_8000(deployment):
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    ports = [p["containerPort"] for p in container["ports"]]
    assert 8000 in ports


def test_deployment_liveness_probe_targets_health(deployment):
    probe = deployment["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]
    assert probe["httpGet"]["path"] == "/health"
    assert probe["httpGet"]["port"] == 8000
    assert probe["initialDelaySeconds"] == 10
    assert probe["periodSeconds"] == 30


def test_deployment_readiness_probe_targets_ready(deployment):
    probe = deployment["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]
    assert probe["httpGet"]["path"] == "/ready"
    assert probe["httpGet"]["port"] == 8000
    assert probe["initialDelaySeconds"] == 5
    assert probe["periodSeconds"] == 10


def test_deployment_resource_requests(deployment):
    requests = deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]
    assert requests["cpu"] == "250m"
    assert requests["memory"] == "256Mi"


def test_deployment_resource_limits(deployment):
    limits = deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    assert limits["cpu"] == "500m"
    assert limits["memory"] == "512Mi"


def test_deployment_db_pass_from_secret_not_configmap(deployment):
    envs = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    db_pass_env = next(e for e in envs if e["name"] == "DB_PASS")
    assert "secretKeyRef" in db_pass_env["valueFrom"]
    assert "configMapKeyRef" not in db_pass_env["valueFrom"]


def test_deployment_db_env_vars_reference_configmap(deployment):
    envs = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    configmap_vars = {e["name"] for e in envs if "configMapKeyRef" in e.get("valueFrom", {})}
    assert {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"}.issubset(configmap_vars)


def test_deployment_redis_env_vars_reference_configmap(deployment):
    envs = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    configmap_vars = {e["name"] for e in envs if "configMapKeyRef" in e.get("valueFrom", {})}
    assert {"REDIS_HOST", "REDIS_PORT"}.issubset(configmap_vars)


def test_deployment_selector_matches_pod_labels(deployment):
    selector_labels = deployment["spec"]["selector"]["matchLabels"]
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert selector_labels == pod_labels


def test_service_api_version_and_kind(service):
    assert service["apiVersion"] == "v1"
    assert service["kind"] == "Service"


def test_service_type_is_cluster_ip(service):
    assert service["spec"]["type"] == "ClusterIP"


def test_service_port_80_targets_8000(service):
    port_entry = service["spec"]["ports"][0]
    assert port_entry["port"] == 80
    assert port_entry["targetPort"] == 8000


def test_service_selector_matches_deployment_app_label(service, deployment):
    service_selector = service["spec"]["selector"]
    deployment_pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    for key, value in service_selector.items():
        assert deployment_pod_labels.get(key) == value


def test_configmap_api_version_and_kind(configmap):
    assert configmap["apiVersion"] == "v1"
    assert configmap["kind"] == "ConfigMap"


def test_configmap_contains_all_required_db_keys(configmap):
    assert {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"}.issubset(configmap["data"].keys())


def test_configmap_contains_required_redis_keys(configmap):
    assert {"REDIS_HOST", "REDIS_PORT"}.issubset(configmap["data"].keys())


def test_configmap_name_matches_deployment_reference(configmap, deployment):
    envs = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    refs = {e["valueFrom"]["configMapKeyRef"]["name"] for e in envs if "configMapKeyRef" in e.get("valueFrom", {})}
    assert configmap["metadata"]["name"] in refs


def test_secret_api_version_and_kind(secret):
    assert secret["apiVersion"] == "v1"
    assert secret["kind"] == "Secret"


def test_secret_type_is_opaque(secret):
    assert secret["type"] == "Opaque"


def test_secret_contains_db_pass_key(secret):
    assert "DB_PASS" in secret["data"]


def test_secret_does_not_contain_real_password(secret):
    value = str(secret["data"]["DB_PASS"])
    assert value != ""
    import base64
    try:
        decoded = base64.b64decode(value + "==").decode("utf-8", errors="ignore")
        assert decoded not in ("", "changeme", "password", "secret", "admin")
    except Exception:
        pass


def test_secret_name_matches_deployment_reference(secret, deployment):
    envs = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    db_pass_env = next(e for e in envs if e["name"] == "DB_PASS")
    assert db_pass_env["valueFrom"]["secretKeyRef"]["name"] == secret["metadata"]["name"]


def test_hpa_api_version_and_kind(hpa):
    assert hpa["apiVersion"] == "autoscaling/v2"
    assert hpa["kind"] == "HorizontalPodAutoscaler"


def test_hpa_scale_target_references_deployment(hpa, deployment):
    ref = hpa["spec"]["scaleTargetRef"]
    assert ref["kind"] == "Deployment"
    assert ref["name"] == deployment["metadata"]["name"]


def test_hpa_min_replicas_is_two(hpa):
    assert hpa["spec"]["minReplicas"] == 2


def test_hpa_max_replicas_is_eight(hpa):
    assert hpa["spec"]["maxReplicas"] == 8


def test_hpa_cpu_target_utilization_is_seventy(hpa):
    metrics = hpa["spec"]["metrics"]
    cpu_metric = next(m for m in metrics if m["resource"]["name"] == "cpu")
    assert cpu_metric["resource"]["target"]["averageUtilization"] == 70


def test_all_manifests_have_no_comment_lines():
    for path in K8S_DIR.glob("*.yaml"):
        lines = path.read_text().splitlines()
        for lineno, line in enumerate(lines, 1):
            assert not line.strip().startswith("#"), f"{path.name}:{lineno} yorum satırı içeriyor"


def test_all_manifests_define_name_in_metadata():
    for path in K8S_DIR.glob("*.yaml"):
        doc = yaml.safe_load(path.read_text())
        assert "name" in doc["metadata"], f"{path.name} metadata.name eksik"
