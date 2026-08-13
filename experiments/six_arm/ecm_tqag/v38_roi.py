"""Target-conditioned ROI observation contract for public ECM-TQAG tests.

ROIs are derived from preregistered source geometry. Provider-visible requests
contain only cropped pixels and symbolic occurrence addressing; sealed labels,
canonical target IDs, and full-image bounding boxes are not exposed.
"""
from __future__ import annotations

import base64
import io
import math
import re
import unicodedata
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from PIL import Image

SCHEMA = "ecm-tqag.v3.8.roi-observation.v1"
REGISTRY_SCHEMA = "ecm-tqag.v3.8.source-occurrence-registry.v1"
V35_SCHEMA = "ecm-tqag.v3.5.homogeneous-primitives.v1"
COORDINATE_SPACE = "roi_normalized_0_1_top_left_xyxy"
REGISTRY_COORDINATE_SPACE = "crop_normalized_0_1_top_left_xyxy"
ROI_PADDING_RATIO = 0.10
IOU_THRESHOLD = 0.5
COLLECTIONS = ("nodes", "text_blocks", "annotations", "regions", "marks", "values")

_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", "0123456789+-=()")
_PRIMES = {"′": "'", "’": "'", "‘": "'", "‵": "'", "ʹ": "'", "＇": "'"}
_NUMBER = re.compile(r"(?<![\w])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?![\w])")
_SPACE = re.compile(r"\s+")


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V38:" + reason)


def _number(match: re.Match[str]) -> str:
    raw = match.group(0)
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return raw
    if not value.is_finite():
        return raw
    if value == 0:
        return "0"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _canonical_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _blocked("display_label")
    normalized = unicodedata.normalize("NFC", value).translate(_SUBSCRIPT)
    normalized = "".join(_PRIMES.get(ch, ch) for ch in normalized)
    normalized = _SPACE.sub(" ", normalized).strip()
    return _NUMBER.sub(_number, normalized)


def _unit_bbox(value: Any) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            for item in value
        )
    ):
        raise _blocked("bbox_shape")
    box = [float(item) for item in value]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise _blocked("bbox_ambiguous")
    return box


def _intersection(left: list[float], right: list[float]) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )


def _bbox_iou(left: list[float], right: list[float]) -> float:
    intersection = _intersection(left, right)
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def validate_source_occurrence_registry(value: Any, *, image_index: int) -> dict[str, Any]:
    """Validate a closed, source-authored occurrence registry."""
    required = {
        "schema",
        "image_index",
        "coordinate_space",
        "observation_region",
        "occurrences",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != required
        or value.get("schema") != REGISTRY_SCHEMA
        or value.get("image_index") != image_index
        or value.get("coordinate_space") != REGISTRY_COORDINATE_SPACE
    ):
        raise _blocked("source_registry_schema")

    region = value["observation_region"]
    if (
        not isinstance(region, Mapping)
        or set(region) != {"id", "bbox"}
        or not isinstance(region.get("id"), str)
        or not region["id"]
    ):
        raise _blocked("source_region")
    region_box = _unit_bbox(region["bbox"])

    rows = value["occurrences"]
    if not isinstance(rows, list) or not rows:
        raise _blocked("source_occurrences")
    row_keys = {
        "occurrence_id",
        "source_address",
        "ordinal",
        "region_id",
        "collection",
        "bbox_slot",
        "semantic_label",
        "source_bbox",
        "canonical_target_id",
    }
    seen_occurrences: set[str] = set()
    seen_addresses: set[str] = set()
    seen_ordinals: set[int] = set()
    seen_slots: set[str] = set()
    seen_targets: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping) or set(row) != row_keys:
            raise _blocked("source_occurrence_shape")
        occurrence_id = row["occurrence_id"]
        address = row["source_address"]
        ordinal = row["ordinal"]
        slot = row["bbox_slot"]
        if not all(isinstance(item, str) and item for item in (occurrence_id, address, slot)):
            raise _blocked("source_address")
        if occurrence_id in seen_occurrences:
            raise _blocked("occurrence_collision")
        if (
            address in seen_addresses
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 1
            or ordinal in seen_ordinals
            or slot in seen_slots
        ):
            raise _blocked("ambiguous_source_address")
        if row["region_id"] != region["id"] or row["collection"] not in COLLECTIONS:
            raise _blocked("source_address_mismatch")
        _canonical_key(row["semantic_label"])
        target = row["canonical_target_id"]
        if target is not None and (
            not isinstance(target, str) or not target or target in seen_targets
        ):
            raise _blocked("canonical_target_mapping")
        box = _unit_bbox(row["source_bbox"])
        box_area = (box[2] - box[0]) * (box[3] - box[1])
        if _intersection(box, region_box) < box_area - 1e-12:
            raise _blocked("source_address_mismatch")

        seen_occurrences.add(occurrence_id)
        seen_addresses.add(address)
        seen_ordinals.add(ordinal)
        seen_slots.add(slot)
        if target is not None:
            seen_targets.add(target)
        cleaned.append({**dict(row), "source_bbox": box})

    cleaned.sort(key=lambda item: item["ordinal"])
    return {
        "schema": REGISTRY_SCHEMA,
        "image_index": image_index,
        "coordinate_space": REGISTRY_COORDINATE_SPACE,
        "observation_region": {"id": region["id"], "bbox": region_box},
        "occurrences": cleaned,
    }


def _target_slot(
    source_registry: Any, *, image_index: int, occurrence_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = validate_source_occurrence_registry(source_registry, image_index=image_index)
    matches = [
        row for row in registry["occurrences"] if row["occurrence_id"] == occurrence_id
    ]
    if len(matches) != 1:
        raise _blocked("source_address")
    slot = matches[0]
    if slot["canonical_target_id"] is None:
        raise _blocked("non_target_occurrence")
    return registry, slot


def select_single_target_occurrence(source_registry: Any, *, image_index: int) -> str:
    """Return the sole preregistered target occurrence, failing closed otherwise."""
    registry = validate_source_occurrence_registry(source_registry, image_index=image_index)
    targets = [
        row["occurrence_id"]
        for row in registry["occurrences"]
        if row["canonical_target_id"] is not None
    ]
    if len(targets) != 1:
        raise _blocked("target_occurrence_count")
    return targets[0]


def derive_target_roi(
    source_registry: Any, *, image_index: int, occurrence_id: str
) -> list[float]:
    """Derive a deterministic clipped ROI solely from sealed source geometry."""
    _, slot = _target_slot(
        source_registry, image_index=image_index, occurrence_id=occurrence_id
    )
    x1, y1, x2, y2 = slot["source_bbox"]
    pad_x = (x2 - x1) * ROI_PADDING_RATIO
    pad_y = (y2 - y1) * ROI_PADDING_RATIO
    return [
        round(max(0.0, x1 - pad_x), 12),
        round(max(0.0, y1 - pad_y), 12),
        round(min(1.0, x2 + pad_x), 12),
        round(min(1.0, y2 + pad_y), 12),
    ]


def roi_bbox_to_global(local_bbox: Any, roi_bbox: Any) -> list[float]:
    """Map ROI-normalized coordinates into full-crop normalized coordinates."""
    local = _unit_bbox(local_bbox)
    roi = _unit_bbox(roi_bbox)
    width = roi[2] - roi[0]
    height = roi[3] - roi[1]
    return [
        roi[0] + local[0] * width,
        roi[1] + local[1] * height,
        roi[0] + local[2] * width,
        roi[1] + local[3] * height,
    ]


def _crop_data_url(image_data_url: str, roi: list[float]) -> str:
    if (
        not isinstance(image_data_url, str)
        or not image_data_url.startswith("data:image/")
        or "," not in image_data_url
    ):
        raise _blocked("image_url")
    header, encoded = image_data_url.split(",", 1)
    if ";base64" not in header:
        raise _blocked("image_url")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            width, height = source.size
            left = round(roi[0] * width)
            top = round(roi[1] * height)
            right = round(roi[2] * width)
            bottom = round(roi[3] * height)
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise _blocked("roi_pixels")
            cropped = source.crop((left, top, right, bottom)).convert("RGB")
    except ValueError:
        raise
    except Exception as exc:
        raise _blocked("image_url") from exc
    stream = io.BytesIO()
    cropped.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def response_format_r6(
    image_index: int, source_registry: Any, *, occurrence_id: str
) -> dict[str, Any]:
    registry, slot = _target_slot(
        source_registry, image_index=image_index, occurrence_id=occurrence_id
    )
    properties = {
        "schema": {"type": "string", "enum": [SCHEMA]},
        "image_index": {"type": "integer", "enum": [image_index]},
        "coordinate_space": {"type": "string", "enum": [COORDINATE_SPACE]},
        "observation_region_id": {
            "type": "string",
            "enum": [registry["observation_region"]["id"]],
        },
        "occurrence_id": {"type": "string", "enum": [slot["occurrence_id"]]},
        "source_address": {"type": "string", "enum": [slot["source_address"]]},
        "display_label": {"type": "string", "minLength": 1},
        "bbox": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }
    return {
        "type": "json_schema",
        "json_schema": {"name": "ecm_tqag_v38_roi", "strict": True, "schema": schema},
    }


def generation_request_r6(
    *, image_index: int, image_data_url: str, source_registry: Any, occurrence_id: str
) -> dict[str, Any]:
    _, slot = _target_slot(
        source_registry, image_index=image_index, occurrence_id=occurrence_id
    )
    roi = derive_target_roi(
        source_registry, image_index=image_index, occurrence_id=occurrence_id
    )
    cropped_url = _crop_data_url(image_data_url, roi)
    noun = slot["collection"][:-1] if slot["collection"].endswith("s") else slot["collection"]
    prompt = (
        "Inspect only this target-conditioned cropped evidence region. Emit the single "
        f"directly pixel-visible {noun} occurrence {slot['occurrence_id']} at source "
        f"address {slot['source_address']}. Preserve its literal visible text without "
        "translation and return a tight bbox in ROI-normalized top-left xyxy coordinates. "
        "Do not infer from outside the supplied pixels. JSON only."
    )
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": cropped_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 600,
        "response_format": response_format_r6(
            image_index, source_registry, occurrence_id=occurrence_id
        ),
    }


def project_roi_to_v35(
    value: Any, *, image_index: int, source_registry: Any, occurrence_id: str
) -> dict[str, Any]:
    """Project one local ROI observation into the closed v3.5 replay shape."""
    registry, slot = _target_slot(
        source_registry, image_index=image_index, occurrence_id=occurrence_id
    )
    required = {
        "schema",
        "image_index",
        "coordinate_space",
        "observation_region_id",
        "occurrence_id",
        "source_address",
        "display_label",
        "bbox",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != required
        or value.get("schema") != SCHEMA
        or value.get("image_index") != image_index
        or value.get("coordinate_space") != COORDINATE_SPACE
        or value.get("observation_region_id") != registry["observation_region"]["id"]
        or value.get("occurrence_id") != slot["occurrence_id"]
        or value.get("source_address") != slot["source_address"]
    ):
        raise _blocked("schema")
    label = value.get("display_label")
    if _canonical_key(label) != _canonical_key(slot["semantic_label"]):
        raise _blocked("semantic_mismatch")
    roi = derive_target_roi(
        registry, image_index=image_index, occurrence_id=occurrence_id
    )
    global_bbox = roi_bbox_to_global(value.get("bbox"), roi)
    if _bbox_iou(global_bbox, slot["source_bbox"]) < IOU_THRESHOLD:
        raise _blocked("source_geometry_mismatch")
    output: dict[str, Any] = {
        "schema": V35_SCHEMA,
        "image_index": image_index,
        "coordinate_space": "normalized_0_1",
        **{collection: [] for collection in COLLECTIONS},
        "groups": [],
    }
    output[slot["collection"]].append(
        {
            "id": slot["canonical_target_id"],
            "display_label": label,
            "bbox": global_bbox,
        }
    )
    return output


__all__ = [
    "COLLECTIONS",
    "COORDINATE_SPACE",
    "IOU_THRESHOLD",
    "REGISTRY_SCHEMA",
    "ROI_PADDING_RATIO",
    "SCHEMA",
    "derive_target_roi",
    "generation_request_r6",
    "project_roi_to_v35",
    "response_format_r6",
    "roi_bbox_to_global",
    "select_single_target_occurrence",
    "validate_source_occurrence_registry",
]
