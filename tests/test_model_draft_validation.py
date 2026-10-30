from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from routers.uploads import require_model_edit, router  # noqa: E402
from svg_kit.validate import validate_content  # noqa: E402


SVG_TEXT = '<svg xmlns="http://www.w3.org/2000/svg"><g id="ARM_REAL" data-pid="ARM_REAL" /></svg>'


def make_motion(target="ARM_REAL"):
    return {
        "schema_version": "1.1",
        "document": {"viewBox": "0 0 100 100"},
        "parts": [{"part_id": "ARM_REAL"}],
        "ext": {"part_aliases": {"ARM": "ARM_REAL"}},
        "motions": [{
            "step": "MOVE",
            "rules": [{
                "target_part_id": target,
                "actions": [{"type": "opacity", "value": 1}],
            }],
        }],
    }


def test_validate_content_accepts_valid_draft():
    errors, warnings = validate_content(SVG_TEXT, make_motion())
    assert errors == []
    assert warnings == []


def test_validate_content_accepts_aliases_and_runtime_targets():
    for target in ("ARM", "{PORT}_CST"):
        errors, _ = validate_content(SVG_TEXT, make_motion(target))
        assert errors == []


def test_validate_content_reports_missing_target():
    errors, _ = validate_content(SVG_TEXT, make_motion("MISSING"))
    assert any("target_part_id=MISSING" in error for error in errors)


def test_validate_draft_post_uses_shared_rules_and_permission():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_model_edit] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/api/uploads/models/validate-draft",
        json={"svg_text": SVG_TEXT, "motion": make_motion("ARM")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert body["summary"] == {"id_count": 1, "part_count": 1, "motion_count": 1}
    route = next(route for route in router.routes if getattr(route, "path", "") == "/api/uploads/models/validate-draft")
    assert any(dependency.call == require_model_edit for dependency in route.dependant.dependencies)
