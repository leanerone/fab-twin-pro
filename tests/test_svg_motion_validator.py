import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))

from svg_kit.validate import check_motion, cross_check  # noqa: E402


VALIDATOR = ROOT / "models" / "svg_kit" / "validate.py"
SVG_TEXT = (
    '<svg xmlns="http://www.w3.org/2000/svg">'
    '<g id="PART" data-pid="PART" />'
    '<g id="STATIC" data-pid="STATIC" />'
    '</svg>'
)


def make_motion(actions, target="PART"):
    return {
        "schema_version": "1.1",
        "document": {},
        "motions": [{
            "step": "MOVE",
            "rules": [{"target_part_id": target, "actions": actions}],
        }],
    }


def write_case(tmp_path, motion, svg_text=SVG_TEXT):
    svg_path = tmp_path / "machine.svg"
    motion_path = tmp_path / "machine.motion.json"
    svg_path.write_text(svg_text, encoding="utf-8")
    motion_path.write_text(json.dumps(motion), encoding="utf-8")
    return svg_path, motion_path


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(VALIDATOR), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize("angle", [0, 90, -12.5])
def test_rotate_accepts_finite_numeric_angle(angle):
    errors, warnings = check_motion(make_motion([{"type": "rotate", "angle": angle}]))
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("action", [
    {"type": "rotate"},
    {"type": "rotate", "angle_to": 90},
])
def test_rotate_requires_angle_and_does_not_accept_angle_to(action):
    errors, warnings = check_motion(make_motion([action]))
    assert len(errors) == 1
    assert "缺少 angle" in errors[0]
    assert warnings == []


def test_rotate_does_not_validate_angle_to_when_angle_is_valid():
    action = {"type": "rotate", "angle": 90, "angle_to": "ignored"}
    errors, warnings = check_motion(make_motion([action]))
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("angle", [None, "90", True, False, [], {}])
def test_rotate_rejects_non_numeric_angle(angle):
    errors, warnings = check_motion(make_motion([{"type": "rotate", "angle": angle}]))
    assert len(errors) == 1
    assert "必须是数值" in errors[0]
    assert warnings == []


@pytest.mark.parametrize("angle", [float("nan"), float("inf"), float("-inf")])
def test_rotate_rejects_non_finite_angle(angle):
    errors, warnings = check_motion(make_motion([{"type": "rotate", "angle": angle}]))
    assert len(errors) == 1
    assert "NaN/Infinity" in errors[0]
    assert warnings == []


def test_rotate_runtime_angle_placeholder_is_warning():
    action = {"type": "rotate", "angle": "{ARM_ANGLE}"}
    errors, warnings = check_motion(make_motion([action]))
    assert errors == []
    assert len(warnings) == 1
    assert "rotate.angle" in warnings[0]
    assert "占位符" in warnings[0]


def test_unknown_action_type_is_error():
    errors, warnings = check_motion(make_motion([{"type": "spin"}]))
    assert len(errors) == 1
    assert "类型 'spin'" in errors[0]
    assert warnings == []


def test_empty_actions_is_warning():
    errors, warnings = check_motion(make_motion([]))
    assert errors == []
    assert len(warnings) == 1
    assert "actions 为空" in warnings[0]


def test_unused_part_is_warning():
    errors, warnings = cross_check(
        SVG_TEXT,
        make_motion([{"type": "opacity", "to": 1}]),
    )
    assert errors == []
    assert len(warnings) == 1
    assert "未被任何 Motion 引用" in warnings[0]
    assert "STATIC" in warnings[0]


def test_runtime_target_placeholder_is_warning():
    motion = make_motion([{"type": "opacity", "to": 1}])
    motion["motions"][0]["rules"].append({
        "target_part_id": "{PORT}_CST",
        "actions": [{"type": "visibility", "to": True}],
    })
    errors, warnings = cross_check(
        '<svg xmlns="http://www.w3.org/2000/svg"><g id="PART" data-pid="PART" /></svg>',
        motion,
    )
    assert errors == []
    assert len(warnings) == 1
    assert "运行时占位符" in warnings[0]


def test_cli_returns_one_for_error(tmp_path):
    svg_path, motion_path = write_case(
        tmp_path,
        make_motion([{"type": "rotate"}]),
    )
    result = run_cli(svg_path, motion_path)
    assert result.returncode == 1
    assert "[ERROR]" in result.stdout
    assert "缺少 angle" in result.stdout


def test_cli_returns_zero_for_warnings_only(tmp_path):
    svg_path, motion_path = write_case(tmp_path, make_motion([], target="STATIC"))
    result = run_cli(svg_path, motion_path)
    assert result.returncode == 0
    assert "[WARN]" in result.stdout
    assert "[ERROR]" not in result.stdout
    assert "结果: 通过" in result.stdout


def test_cli_returns_two_for_argument_error():
    result = run_cli()
    assert result.returncode == 2
    assert "用法:" in result.stdout
