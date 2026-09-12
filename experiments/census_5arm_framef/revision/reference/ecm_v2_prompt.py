#!/usr/bin/env python3
"""ECM-v2 arm: the prompt that states the division of labour the gates check.

WHY A NEW ARM RATHER THAN AN EDITED PROMPT
------------------------------------------
`official/PROMPT_SCHEMA_CONTRACT.json` is sealed and carries the three arms the
reported censuses used. `ecm_tqag.v310_runner.build_generation_request` rejects
any arm outside the frozen `ARMS` tuple. Both are audit-bound, so ECM-v2 is added
as a FOURTH arm with a local prompt and a local request builder, exactly as
`round2c_routes` added substituted judge routes without touching sealed code.

The three baseline arms are untouched, so the census remains paired: every chunk
is attempted by all four arms and each chunk is its own control.

WHAT THE PROMPT ADDS OVER `ecm_full`
------------------------------------
`ecm_full` already asks for a verbatim quotation, a content-hashed figure, and a
question that "would not be answerable if either channel were missing". The audit
in `ecm_v2_gates` showed that last clause had no mechanical gate, and the measured
consequence was that the returned quotation already contained the whole answer in
58% of admitted frame-D items and 79% of frame-E items.

ECM-v2 changes the instruction from a property of the item to a CONSTRUCTION RULE
with a checkable consequence:

    the TEXT quotation establishes what the question is ABOUT;
    the FIGURE supplies what the question ASKS FOR.

and states the three gates in the prompt, so the arm is told the conditions its
response will be checked against. This is deliberate and is the same design
decision the `structured_no_contract` control was built to isolate: disclosure of
conditions is not the same as fixing the order of work, and the baseline arms
already separate those two effects.

ROLE CONDITIONING
-----------------
The prompt is also told what KIND of figure the chunk carries, because the
question shape that needs a figure differs by kind, and the corpus itself records
the kind:

    table      -> ask for a cell reached by row x column ("in row X, column Y")
    diagram    -> ask for a relation an arrow or nesting expresses
    pictorial  -> ask for a label, region, or spatial fact shown in the image

Roles are recovered from the section builder's own `regions[].kind`, so nothing is
re-detected here. Frame-F distribution: 36 table, 24 pictorial.

The role does NOT relax any gate. It only tells the generator which question form
can satisfy them on this chunk.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

# The sealed evidence verifier and response-format builder live in the private
# experiment tree. The published copy of this repository ships only the public
# `ecm_tqag` package, so the imports are guarded: the PROMPT TEXT and
# `render_messages` are inspectable and testable without them, while
# `build_generation_request_ecm_v2` -- the only function that touches evidence
# bytes or builds a paid request -- fails closed with an explicit reason when
# they are absent. Inside the private tree both imports resolve and behaviour is
# unchanged.
try:                                                  # pragma: no cover
    from ecm_tqag.v310_runner import _verified_evidence
    from ecm_tqag.v310_validation import generation_response_format
    SEALED_HELPERS_AVAILABLE = True
except ImportError:                                   # pragma: no cover
    _verified_evidence = None                         # type: ignore[assignment]
    generation_response_format = None                 # type: ignore[assignment]
    SEALED_HELPERS_AVAILABLE = False

QUESTION_TYPES = ("short_answer", "multiple_choice")

ARM_NAME = "ecm_v2"
CONTROL_ARM_NAME = "ecm_v2_disclosed"

# ARMS of the ECM-v2 census, in report order. The three sealed baseline arms are
# run unchanged alongside these two, so every chunk is attempted by five arms and
# each chunk remains its own control.
ECM_V2_ARMS = (ARM_NAME, CONTROL_ARM_NAME)

# What question shape can satisfy the gates, per figure role. Kept short: the
# system prompt already carries the rule, this only names the admissible form.
ROLE_GUIDANCE = {
    "table": (
        "BẢNG: đặt câu hỏi hỏi một Ô của bảng, xác định bởi giao của một HÀNG và "
        "một CỘT (ví dụ: ở hàng X thì cột Y ghi gì). Đáp án là nội dung ô đó."
    ),
    "diagram": (
        "SƠ ĐỒ: đặt câu hỏi hỏi một QUAN HỆ mà mũi tên hoặc thứ bậc trong sơ đồ "
        "thể hiện (ví dụ: bộ phận nào trực thuộc bộ phận nào, bước nào đứng sau "
        "bước nào). Đáp án là quan hệ hoặc thành phần đọc được từ sơ đồ."
    ),
    "pictorial": (
        "HÌNH ẢNH/BẢN ĐỒ: đặt câu hỏi hỏi một NHÃN, một VÙNG, hoặc một dữ kiện "
        "KHÔNG GIAN chỉ hiển thị trong hình (ví dụ: vùng được tô tên là gì, đối "
        "tượng nào nằm ở vị trí nào). Đáp án là nhãn hoặc dữ kiện đó."
    ),
}

SYSTEM = (
    "Bạn tạo đúng một mục TQA đa phương thức bằng tiếng Việt từ duy nhất gói "
    "nguồn được cung cấp. Thực hiện nội bộ, không xuất chuỗi suy luận.\n"
    "NGUYÊN TẮC PHÂN CÔNG HAI KÊNH (bắt buộc): trích dẫn VĂN BẢN xác lập câu hỏi "
    "HỎI VỀ CÁI GÌ; HÌNH cung cấp CÁI MÀ CÂU HỎI YÊU CẦU TRẢ LỜI. Hai kênh không "
    "được lặp lại nhau.\n"
    "Bốn bước: (1) ĐỌC HÌNH trước: xác định trong hình một dữ kiện cụ thể "
    "(ô của bảng, quan hệ trong sơ đồ, nhãn trong ảnh) sẽ làm ĐÁP ÁN. (2) CHỌN "
    "TRÍCH DẪN: một chuỗi con nguyên văn của VĂN BẢN NGUỒN nêu chủ đề hoặc bối "
    "cảnh của dữ kiện đó, nhưng KHÔNG chứa chính đáp án. (3) NIÊM PHONG tuple "
    "(question_type, answer, text_evidence_quote, image_sha256) rồi mới soạn câu "
    "hỏi; không đổi bằng chứng để hợp thức hoá câu hỏi. (4) TỰ KIỂM ba cổng dưới "
    "đây trước khi xuất.\n"
    "BA CỔNG SẼ ĐƯỢC KIỂM CƠ HỌC trên phản hồi của bạn:\n"
    "G6 answer KHÔNG được là chuỗi con của text_evidence_quote (so sánh không "
    "phân biệt hoa thường). Nếu đọc trích dẫn là đã trả lời được thì mục bị loại.\n"
    "G7 answer phải chứa ít nhất 2 từ nội dung xuất hiện trong chữ nhận dạng "
    "được từ hình.\n"
    "G8 visual_evidence.description phải chứa ít nhất 3 từ nội dung xuất hiện "
    "trong chữ nhận dạng được từ hình; hãy mô tả CHỮ VÀ CẤU TRÚC THẤY TRONG HÌNH, "
    "không mô tả suy đoán và không nói 'hình chụp đoạn văn'.\n"
    "Với multiple_choice: đúng bốn lựa chọn khác nhau, chỉ một đúng, answer phải "
    "chép nguyên văn chuỗi của lựa chọn đúng; các nhiễu hợp lý nhưng không được "
    "nguồn hỗ trợ. Chỉ trả một JSON object, không thêm giải thích ngoài JSON."
)

USER_TEMPLATE = (
    "VĂN BẢN NGUỒN:\n{source_text}\n\n"
    "CẤU TRÚC TÀI LIỆU:\n{document_structure_json}\n\n"
    "LOẠI HÌNH TRONG MỤC NÀY: {figure_role}\n"
    "{role_guidance}\n\n"
    "LOẠI CÂU HỎI ĐÃ ẤN ĐỊNH: {question_type}\n\n"
    "SHA-256 ẢNH HỢP LỆ: {image_hashes_json}\n\n"
    "Hãy đọc hình trước, chọn đáp án từ hình, chọn trích dẫn nêu bối cảnh mà "
    "KHÔNG chứa đáp án, niêm phong tuple, tự kiểm G6/G7/G8, rồi chỉ xuất object "
    "cuối. text_evidence_quote phải là chuỗi con nguyên văn của VĂN BẢN NGUỒN; "
    "visual_evidence.image_sha256 phải thuộc danh sách hợp lệ; "
    "necessity_rationale phải nêu cụ thể dữ kiện nào trong hình cung cấp đáp án."
)


# ---------------------------------------------------------------------------
# the length-matched disclosure control
# ---------------------------------------------------------------------------
# WHY THIS ARM EXISTS
#   The ECM-v2 system prompt is longer than `ecm_full`'s (+433 characters over
#   system+user). Prompt length is a confound: a longer prompt could raise
#   admission by attention alone. The reported census handles exactly this with a
#   gate-disclosed control at matched length (manuscript: "At matched prompt
#   length (1604 against 1623 characters)"), which is what licenses the claim
#   that ORDERING rather than DISCLOSURE carries the effect.
#
#   This arm reproduces that design for ECM-v2. It names the same division of
#   labour, states the same three gates verbatim, and carries the same role
#   guidance -- so the generator is told everything it will be checked against --
#   but it does NOT fix the order of work: no "read the figure first", no
#   answer-first plan, no seal step. The order of construction is left free.
#
#   If ECM-v2 separates from this control, the effect is attributable to fixing
#   the construction order. If it does not, the honest reading is that stating
#   the conditions is what matters, and that is a weaker and different claim.
DISCLOSED_SYSTEM = (
    "Bạn tạo đúng một mục TQA đa phương thức bằng tiếng Việt từ duy nhất gói "
    "nguồn được cung cấp. Thực hiện nội bộ, không xuất chuỗi suy luận.\n"
    "NGUYÊN TẮC PHÂN CÔNG HAI KÊNH (bắt buộc): trích dẫn VĂN BẢN xác lập câu hỏi "
    "HỎI VỀ CÁI GÌ; HÌNH cung cấp CÁI MÀ CÂU HỎI YÊU CẦU TRẢ LỜI. Hai kênh không "
    "được lặp lại nhau.\n"
    "Bạn tự quyết định trình tự làm việc: đọc hình trước hay đọc văn bản trước, "
    "soạn câu hỏi trước hay chốt đáp án trước, chọn bằng chứng trước hay sau khi "
    "đã có câu hỏi, đều được. Không có bước bắt buộc nào về thứ tự và không có "
    "bước lập kế hoạch bắt buộc. Bạn không cần niêm phong bằng chứng trước khi "
    "soạn câu hỏi, và nếu thấy cần thì có thể điều chỉnh trích dẫn, ảnh hoặc câu "
    "hỏi trong lúc làm. Hãy tổ chức công việc theo cách bạn thấy hiệu quả nhất, "
    "miễn là kết quả cuối cùng thoả ba cổng nêu dưới đây.\n"
    "BA CỔNG SẼ ĐƯỢC KIỂM CƠ HỌC trên phản hồi của bạn:\n"
    "G6 answer KHÔNG được là chuỗi con của text_evidence_quote (so sánh không "
    "phân biệt hoa thường). Nếu đọc trích dẫn là đã trả lời được thì mục bị loại.\n"
    "G7 answer phải chứa ít nhất 2 từ nội dung xuất hiện trong chữ nhận dạng "
    "được từ hình.\n"
    "G8 visual_evidence.description phải chứa ít nhất 3 từ nội dung xuất hiện "
    "trong chữ nhận dạng được từ hình; hãy mô tả CHỮ VÀ CẤU TRÚC THẤY TRONG HÌNH, "
    "không mô tả suy đoán và không nói 'hình chụp đoạn văn'.\n"
    "Với multiple_choice: đúng bốn lựa chọn khác nhau, chỉ một đúng, answer phải "
    "chép nguyên văn chuỗi của lựa chọn đúng; các nhiễu hợp lý nhưng không được "
    "nguồn hỗ trợ. Chỉ trả một JSON object, không thêm giải thích ngoài JSON."
)

DISCLOSED_USER_TEMPLATE = (
    "VĂN BẢN NGUỒN:\n{source_text}\n\n"
    "CẤU TRÚC TÀI LIỆU:\n{document_structure_json}\n\n"
    "LOẠI HÌNH TRONG MỤC NÀY: {figure_role}\n"
    "{role_guidance}\n\n"
    "LOẠI CÂU HỎI ĐÃ ẤN ĐỊNH: {question_type}\n\n"
    "SHA-256 ẢNH HỢP LỆ: {image_hashes_json}\n\n"
    "Hãy tạo mục thoả ba cổng G6/G7/G8 nêu trên, theo trình tự làm việc bạn tự "
    "chọn và không cần niêm phong bằng chứng trước, rồi chỉ xuất object cuối. "
    "text_evidence_quote phải là chuỗi con "
    "nguyên văn của VĂN BẢN NGUỒN; visual_evidence.image_sha256 phải thuộc danh "
    "sách hợp lệ; necessity_rationale phải nêu cụ thể dữ kiện nào trong hình "
    "cung cấp đáp án."
)

# arm -> (system, user template)
_PROMPTS = {
    ARM_NAME: (SYSTEM, USER_TEMPLATE),
    CONTROL_ARM_NAME: (DISCLOSED_SYSTEM, DISCLOSED_USER_TEMPLATE),
}


def prompt_lengths() -> dict[str, dict[str, int]]:
    """Character budget per ECM-v2 arm, so the length match is checkable."""
    return {
        arm: {"system": len(system), "user_template": len(user),
              "total": len(system) + len(user)}
        for arm, (system, user) in _PROMPTS.items()
    }


def blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_ECM_V2_PROMPT:" + reason)


def render_messages(
    *,
    arm: str = ARM_NAME,
    question_type: str,
    source_text: str,
    document_structure: Any,
    image_hashes: Sequence[str],
    figure_role: str,
) -> list[dict[str, str]]:
    """Render the generation messages for one ECM-v2 arm.

    Mirrors `v310_validation.render_generation_messages` in shape -- same
    placeholders, same JSON serialisation of the structure -- so the only
    difference from a baseline arm is the prompt text and the two role fields.

    `arm` selects between the ordered contract and its length-matched disclosure
    control. Both receive identical evidence, identical role guidance and the
    same three stated gates; only the ordering clauses differ.
    """
    if arm not in _PROMPTS:
        raise blocked("ARM:" + str(arm))
    if figure_role not in ROLE_GUIDANCE:
        raise blocked("FIGURE_ROLE:" + str(figure_role))
    if question_type not in QUESTION_TYPES:
        raise blocked("QUESTION_TYPE:" + str(question_type))
    if SEALED_HELPERS_AVAILABLE:
        generation_response_format(question_type)  # sealed validator, when present
    system, template = _PROMPTS[arm]
    user = template.format(
        source_text=source_text,
        document_structure_json=json.dumps(document_structure, ensure_ascii=False,
                                           sort_keys=True),
        question_type=question_type,
        image_hashes_json=json.dumps(list(image_hashes), ensure_ascii=False),
        figure_role=figure_role,
        role_guidance=ROLE_GUIDANCE[figure_role],
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def build_generation_request_ecm_v2(
    package: Mapping[str, Any], *, question_type: str, arm: str = ARM_NAME
) -> dict[str, Any]:
    """Generation request for one ECM-v2 arm.

    Byte-identical to the sealed builder in evidence handling: it calls the sealed
    `_verified_evidence`, so image bytes and hashes are re-verified and the
    evidence digest is computed the same way. Only the rendered prompt differs,
    and the arm name is not passed through the frozen `ARMS` allow-list because
    these arms are local to ECM-v2.
    """
    if not SEALED_HELPERS_AVAILABLE:
        raise blocked("SEALED_HELPERS_UNAVAILABLE:ecm_tqag.v310_runner")
    if arm not in _PROMPTS:
        raise blocked("ARM:" + str(arm))
    if package.get("question_type") != question_type:
        raise blocked("QUESTION_TYPE")
    structure = (package.get("evidence") or {}).get("document_structure") or {}
    role = structure.get("figure_role")
    if role not in ROLE_GUIDANCE:
        raise blocked("FIGURE_ROLE_MISSING_IN_PACKAGE")

    evidence = _verified_evidence(package)
    rendered = render_messages(
        arm=arm,
        question_type=question_type,
        source_text=evidence["text"],
        document_structure=evidence["structure"],
        image_hashes=evidence["image_hashes"],
        figure_role=role,
    )
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": rendered[1]["content"]},
        *evidence["image_parts"],
    ]
    payload = {
        "messages": [rendered[0], {"role": "user", "content": user_content}],
        "temperature": 0,
        "max_tokens": 1024,
        "response_format": generation_response_format(question_type),
    }
    import hashlib

    return {
        "model": None,          # set by the caller from the frozen generator
        "payload": payload,
        "evidence_sha256": evidence["evidence_sha256"],
        "method_prompt_sha256": hashlib.sha256(
            rendered[0]["content"].encode("utf-8")).hexdigest(),
        "image_hashes": evidence["image_hashes"],
        "source_text": evidence["text"],
        "question_type": question_type,
        "figure_role": role,
        "arm": arm,
    }


__all__ = [
    "ARM_NAME",
    "CONTROL_ARM_NAME",
    "ECM_V2_ARMS",
    "ROLE_GUIDANCE",
    "SYSTEM",
    "USER_TEMPLATE",
    "DISCLOSED_SYSTEM",
    "DISCLOSED_USER_TEMPLATE",
    "build_generation_request_ecm_v2",
    "prompt_lengths",
    "render_messages",
]
