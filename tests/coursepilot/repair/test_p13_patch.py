import pytest

from coursepilot.repair.models import PatchOperation
from coursepilot.repair.patch import PatchApplyError, apply_patch


def test_patch_is_atomic_and_restricted() -> None:
    source = {"session_plan": [{"teaching_focus": "old", "duration": 45}]}
    result = apply_patch(
        source,
        [
            PatchOperation(
                op="replace",
                path="$.session_plan[0].teaching_focus",
                value="new",
                expected_value="old",
            )
        ],
        allowed_paths=["$.session_plan[0].teaching_focus"],
    )
    assert result["session_plan"][0]["teaching_focus"] == "new"
    assert source["session_plan"][0]["teaching_focus"] == "old"
    with pytest.raises(PatchApplyError):
        apply_patch(
            source,
            [PatchOperation(op="replace", path="$.session_plan[0].duration", value=90)],
            allowed_paths=["$.session_plan[0].teaching_focus"],
        )
