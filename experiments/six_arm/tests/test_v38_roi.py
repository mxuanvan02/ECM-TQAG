from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image

from ecm_tqag import v38_roi


def registry(*, repeated: bool = False):
    rows = [
        {
            "occurrence_id": "occ:synthetic:target:001",
            "source_address": "src:synthetic:target:001",
            "ordinal": 1,
            "region_id": "synthetic:crop",
            "collection": "nodes",
            "bbox_slot": "slot:001",
            "semantic_label": "Target Alpha",
            "source_bbox": [0.20, 0.30, 0.60, 0.50],
            "canonical_target_id": "synthetic:target:alpha",
        }
    ]
    if repeated:
        rows.append(
            {
                "occurrence_id": "occ:synthetic:target:002",
                "source_address": "src:synthetic:target:002",
                "ordinal": 2,
                "region_id": "synthetic:crop",
                "collection": "nodes",
                "bbox_slot": "slot:002",
                "semantic_label": "Target Alpha",
                "source_bbox": [0.65, 0.65, 0.90, 0.85],
                "canonical_target_id": "synthetic:target:beta",
            }
        )
    return {
        "schema": v38_roi.REGISTRY_SCHEMA,
        "image_index": 1,
        "coordinate_space": "crop_normalized_0_1_top_left_xyxy",
        "observation_region": {"id": "synthetic:crop", "bbox": [0, 0, 1, 1]},
        "occurrences": rows,
    }


def image_url(width: int = 100, height: int = 100) -> str:
    image = Image.new("RGB", (width, height), "white")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def decode_image(url: str) -> Image.Image:
    _, encoded = url.split(",", 1)
    return Image.open(io.BytesIO(base64.b64decode(encoded)))


def valid_observation():
    return {
        "schema": v38_roi.SCHEMA,
        "image_index": 1,
        "coordinate_space": v38_roi.COORDINATE_SPACE,
        "observation_region_id": "synthetic:crop",
        "occurrence_id": "occ:synthetic:target:001",
        "source_address": "src:synthetic:target:001",
        "display_label": "Target Alpha",
        "bbox": [1 / 12, 1 / 12, 11 / 12, 11 / 12],
    }


def test_roi_is_deterministic_clipped_and_source_only():
    first = v38_roi.derive_target_roi(
        registry(), image_index=1, occurrence_id="occ:synthetic:target:001"
    )
    second = v38_roi.derive_target_roi(
        registry(), image_index=1, occurrence_id="occ:synthetic:target:001"
    )
    assert first == second == [0.16, 0.28, 0.64, 0.52]


def test_request_crops_pixels_without_exposing_sealed_answer_or_global_bbox():
    payload = v38_roi.generation_request_r6(
        image_index=1,
        image_data_url=image_url(),
        source_registry=registry(),
        occurrence_id="occ:synthetic:target:001",
    )
    serialized = json.dumps(payload)
    assert "Target Alpha" not in serialized
    assert "synthetic:target:alpha" not in serialized
    assert "source_bbox" not in serialized
    assert "0.20" not in serialized and "0.60" not in serialized
    content = payload["messages"][0]["content"]
    assert decode_image(content[1]["image_url"]["url"]).size == (48, 24)
    assert payload["temperature"] == 0


def test_repeated_labels_use_distinct_spatial_rois_and_fail_single_target_selection():
    source = registry(repeated=True)
    one = v38_roi.derive_target_roi(
        source, image_index=1, occurrence_id="occ:synthetic:target:001"
    )
    two = v38_roi.derive_target_roi(
        source, image_index=1, occurrence_id="occ:synthetic:target:002"
    )
    assert one != two
    assert two == [0.625, 0.63, 0.925, 0.87]
    with pytest.raises(ValueError, match="BLOCKED_V38:target_occurrence_count"):
        v38_roi.select_single_target_occurrence(source, image_index=1)


def test_affine_mapping_is_exact_and_deterministic():
    roi = [0.16, 0.28, 0.64, 0.52]
    local = [1 / 12, 1 / 12, 11 / 12, 11 / 12]
    expected = [0.20, 0.30, 0.60, 0.50]
    assert v38_roi.roi_bbox_to_global(local, roi) == pytest.approx(expected)
    assert v38_roi.roi_bbox_to_global(local, roi) == v38_roi.roi_bbox_to_global(local, roi)


def test_wrong_semantics_remain_fail_closed():
    wrong = valid_observation()
    wrong["display_label"] = "Different Target"
    with pytest.raises(ValueError, match="BLOCKED_V38:semantic_mismatch"):
        v38_roi.project_roi_to_v35(
            wrong,
            image_index=1,
            source_registry=registry(),
            occurrence_id="occ:synthetic:target:001",
        )


def test_wrong_geometry_remains_fail_closed():
    wrong = valid_observation()
    wrong["bbox"] = [0.0, 0.0, 0.2, 0.2]
    with pytest.raises(ValueError, match="BLOCKED_V38:source_geometry_mismatch"):
        v38_roi.project_roi_to_v35(
            wrong,
            image_index=1,
            source_registry=registry(),
            occurrence_id="occ:synthetic:target:001",
        )


def test_valid_observation_projects_to_closed_v35_shape():
    projected = v38_roi.project_roi_to_v35(
        valid_observation(),
        image_index=1,
        source_registry=registry(),
        occurrence_id="occ:synthetic:target:001",
    )
    assert projected["schema"] == "ecm-tqag.v3.5.homogeneous-primitives.v1"
    assert projected["nodes"][0]["id"] == "synthetic:target:alpha"
    assert projected["nodes"][0]["bbox"] == pytest.approx([0.20, 0.30, 0.60, 0.50])
    assert projected["groups"] == []
