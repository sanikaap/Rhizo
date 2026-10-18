from pathlib import Path

import pytest

from rhizo.detect import compose, javascript, k8s, python
from rhizo.detect.run import detect


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _edges(d: object) -> set[tuple[str, str, str, str]]:
    return {(e.rel, e.source, e.target, e.provenance) for e in d.unique_edges()}  # type: ignore[attr-defined]


def test_compose_services_depends_on_env_and_resources(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "docker-compose.yml": """
services:
  web:
    build: ./web
    depends_on: [api]
    environment:
      API_URL: http://api:8080/v1
      NODE_ENV: production
  api:
    build: {context: ./services/api}
    depends_on: {db: {condition: service_healthy}}
    environment:
      - DATABASE_URL=postgres://admin:s3cret@db:5432/app
      - CACHE=cache:6379
  db: {image: "postgres:16"}
  cache: {image: "docker.io/library/redis:7-alpine"}
""",
        },
    )
    d = compose.detect(tmp_path)
    assert {n: s.path_prefix for n, s in d.services.items()} == {"web": "web/", "api": "services/api/"}
    assert {n: r.kind for n, r in d.resources.items()} == {"db": "database", "cache": "cache"}
    assert _edges(d) == {
        ("DEPENDS_ON", "web", "api", "declared"),
        ("USES", "api", "db", "declared"),
        ("USES", "api", "cache", "declared"),
    }
    evidence = " ".join(e.evidence for e in d.edges)
    assert "docker-compose.yml" in evidence
    assert "s3cret" not in evidence and "admin" not in evidence


def test_k8s_anywhere_with_service_aliases_and_no_hardcoded_names(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "deploy/apps.yaml": """
apiVersion: apps/v1
kind: Deployment
metadata: {name: orders}
spec:
  template:
    metadata: {labels: {app: orders}}
    spec:
      containers:
        - name: app
          image: acme/orders
          env:
            - {name: BILLING, value: "billing-svc.prod.svc.cluster.local:9000"}
            - {name: STORE, value: "store:5432"}
            - {name: GHOST, value: "nowhere:1"}
---
apiVersion: apps/v1
kind: StatefulSet
metadata: {name: billing}
spec:
  template:
    metadata: {labels: {app: billing}}
    spec: {containers: [{name: app, image: acme/billing}]}
---
apiVersion: v1
kind: Service
metadata: {name: billing-svc}
spec: {selector: {app: billing}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: store}
spec:
  template:
    metadata: {labels: {app: store}}
    spec: {containers: [{name: db, image: "mysql:8"}]}
""",
            "chart/templates/x.yaml": "apiVersion: v1\nkind: Deployment\nmetadata: {{ .Values.name }}\n",
        },
    )
    d = k8s.detect(tmp_path)
    assert set(d.services) == {"orders", "billing"} and set(d.resources) == {"store"}
    assert _edges(d) == {
        ("DEPENDS_ON", "orders", "billing", "declared"),
        ("USES", "orders", "store", "declared"),
    }


def test_python_project_units_and_their_imports(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "services/orders/requirements.txt": "",
            "services/orders/app.py": (
                "import billing_client\nfrom shared.money import Money\nimport demo_pb2\n"
            ),
            "services/orders/demo_pb2.py": "",
            "services/billing/pyproject.toml": "",
            "services/billing/billing_client.py": "from . import nothing\n",
            "services/billing/demo_pb2.py": "",
            "libs/shared/setup.py": "",
            "libs/shared/shared/__init__.py": "",
            "libs/shared/shared/money.py": "def broken(:\n",
        },
    )
    d = python.detect(tmp_path)
    assert set(d.services) == {"orders", "billing", "shared"}
    assert _edges(d) == {
        ("DEPENDS_ON", "orders", "billing", "code"),
        ("DEPENDS_ON", "orders", "shared", "code"),
    }
    assert any(e.evidence == "import billing_client in services/orders/app.py" for e in d.edges)


def test_single_python_package_is_split_into_subpackages(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "src/shop/__init__.py": "",
            "src/shop/cli.py": "from shop.orders import place\n",
            "src/shop/orders/__init__.py": "from shop import payments\n",
            "src/shop/payments/__init__.py": "",
            "src/shop/payments/refund.py": "from ..cli import main\nfrom . import nothing\n",
            "tests/test_x.py": "import shop.orders\n",
            "examples/demo/pyproject.toml": "",
            "examples/demo/app.py": "import shop\n",
        },
    )
    d = python.detect(tmp_path)
    assert set(d.services) == {"shop", "shop.orders", "shop.payments"}
    assert _edges(d) == {
        ("DEPENDS_ON", "shop", "shop.orders", "code"),
        ("DEPENDS_ON", "shop.orders", "shop.payments", "code"),
        ("DEPENDS_ON", "shop.payments", "shop", "code"),
    }


def test_js_workspaces_by_package_name_and_relative_path(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "package.json": '{"name": "monorepo", "workspaces": ["packages/*"]}',
            "packages/web/package.json": '{"name": "@acme/web"}',
            "packages/web/src/app.tsx": (
                "import { client } from '@acme/api/client'\nimport React from 'react'\n"
            ),
            "packages/api/package.json": '{"name": "@acme/api"}',
            "packages/api/index.ts": "const u = require('../utils/src/x')\nexport * from './client'\n",
            "packages/utils/package.json": '{"name": "utils"}',
            "packages/utils/src/x.js": "",
            "packages/web/node_modules/@acme/api/index.js": "import '@acme/web'",
        },
    )
    d = javascript.detect(tmp_path)
    assert set(d.services) == {"acme-web", "acme-api", "utils"}
    assert _edges(d) == {
        ("DEPENDS_ON", "acme-web", "acme-api", "code"),
        ("DEPENDS_ON", "acme-api", "utils", "code"),
    }


def test_detectors_merge_by_directory_and_keep_the_strongest_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "docker-compose.yaml": (
                "services:\n  web: {build: ./web, depends_on: [api]}\n  api: {build: ./api}\n"
            ),
            "web/package.json": '{"name": "storefront-ui"}',
            "web/main.js": "import x from '../api/handler.js'\n",
            "api/package.json": '{"name": "api"}',
            "api/handler.js": "",
        },
    )
    d = detect(tmp_path)
    assert set(d.services) == {"web", "api"}
    assert d.aliases == {"storefront-ui": "web"}
    assert _edges(d) == {("DEPENDS_ON", "web", "api", "declared")}
    assert d.services["web"].language == "javascript"


def test_nothing_detected_in_a_plain_repo(tmp_path: Path) -> None:
    _write(tmp_path, {"README.md": "# notes\n", "notes/a.txt": "x"})
    d = detect(tmp_path)
    assert (d.services, d.edges) == ({}, [])


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="needs symlinks")
def test_symlinks_are_never_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _write(outside, {"docker-compose.yml": "services:\n  leaked: {image: app}\n"})
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docker-compose.yml").symlink_to(outside / "docker-compose.yml")
    (repo / "linked").symlink_to(outside, target_is_directory=True)
    assert detect(repo).services == {}
