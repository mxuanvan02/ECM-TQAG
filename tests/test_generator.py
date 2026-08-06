import copy
import json
from pathlib import Path

import pytest

from ecm_tqag import generate, load_document, replay_provenance, validate_generated, validate_triplet
from ecm_tqag.generator import _compute

ROOT = Path(__file__).parents[1]
LAYOUT = ROOT / "fixtures/documents/layout.json"
PIXEL = ROOT / "fixtures/documents/pixel.json"
BLUE = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAD0lEQVR42mNgYPgPRmAKABf2A/3HkIu0AAAAAElFTkSuQmCC"


def item(out: Path):
    manifest = json.loads((out / "manifest.json").read_text())
    entry = manifest["items"][0]
    record = json.loads((out / entry["tqa_path"]).read_text())
    packages = {p["condition"]: json.loads((out / p["path"]).read_text()) for p in entry["packages"]}
    return manifest, record, packages


def test_layout_counterfactual_and_text_ambiguity(tmp_path):
    out = tmp_path / "out"
    assert generate(LAYOUT, out)["item_count"] == 1
    _, record, packages = item(out)
    assert record["answer"] == "42"
    assert record["answer_frozen_before_question"] is True
    assert "42" not in packages["text_only"]["evidence"]["text"]
    changed = load_document(LAYOUT)
    changed["edges"][0]["target"] = "cell-b"
    answer, _ = _compute(changed, changed["motifs"][0])
    assert answer == "17"
    assert packages["text_only"]["evidence"]["text"] == item(out)[2]["text_only"]["evidence"]["text"]


def test_pixel_counterfactual_changes_only_pixels_and_answer(tmp_path):
    original = load_document(PIXEL)
    red_answer, _ = _compute(original, original["motifs"][0])
    changed = copy.deepcopy(original)
    asset = changed["nodes"][2]["value"]
    asset.update(data=BLUE, byte_length=72, sha256="2d8cfdb8c8da042145179a5c216b5ca859291e03166b6384b716bb0648635abf")
    blue_answer, _ = _compute(changed, changed["motifs"][0])
    assert (red_answer, blue_answer) == ("red", "blue")
    assert original["nodes"][:2] == changed["nodes"][:2] and original["edges"] == changed["edges"]


def test_triplet_identity_nesting_missing_modality_and_hashes(tmp_path):
    out = tmp_path / "out"; generate(PIXEL, out)
    _, _, packages = item(out); triplet = list(packages.values())
    assert validate_triplet(triplet)["status"] == "PASS"
    for mutation in ("item", "question", "layout", "pixel"):
        bad = copy.deepcopy(triplet)
        if mutation == "item": bad[0]["item_id"] = "different"
        elif mutation == "question": bad[1]["question"] += " changed"
        elif mutation == "layout": bad[2]["evidence"]["layout"]["nodes"][0]["value"] += " changed"
        else: bad[2].pop("pixel_asset")
        with pytest.raises(ValueError): validate_triplet(bad)
    with pytest.raises(ValueError): validate_triplet(triplet, {c: "0" * 64 for c in packages})


def test_provenance_receipts_stale_output_and_atomic_replace(tmp_path):
    out = tmp_path / "out"; generate(LAYOUT, out)
    assert replay_provenance(LAYOUT, out)["status"] == "PASS"
    (out / "stale.txt").write_text("stale")
    with pytest.raises(ValueError): validate_generated(out, LAYOUT)
    with pytest.raises(ValueError): generate(LAYOUT, out)
    generate(LAYOUT, out, replace=True)
    assert not (out / "stale.txt").exists()
    manifest, _, _ = item(out)
    entry = manifest["items"][0]; p = out / entry["tqa_path"]
    data = json.loads(p.read_text()); data["answer"] = "tampered"; p.write_text(json.dumps(data))
    with pytest.raises(ValueError): validate_generated(out, LAYOUT)


def test_all_motifs_and_portable_manifest(tmp_path):
    doc = load_document(LAYOUT)
    doc["motifs"].append({"id":"m-layout-two","operation":"layout_relation_value","target":"header","relation":"right_of","prompt_label":"the same header","color_map":None})
    source = tmp_path / "multi.json"; source.write_text(json.dumps(doc))
    out = tmp_path / "out"
    assert generate(source, out)["item_count"] == 2
    manifest = json.loads((out / "manifest.json").read_text())
    assert len({e["item_id"] for e in manifest["items"]}) == 2
    assert "/home/" not in json.dumps(manifest)
