"""Round-2d prompt repair (D3): make the output convention unambiguous.

Round-2c evidence (re-derived from retained raw responses, 24 MCQ attempts):

  - 14 attempts satisfied ``answer == options[correct_option - 1]``  (1-based)
  - only  2 attempts satisfied ``answer == options[correct_option]``  (the gate)
  -      4 attempts were genuine errors (answer matched no option)
  -      4 attempts had other index errors, two of them out of any range (4, 14)

`official/PROMPT_SCHEMA_CONTRACT.json` never states the indexing convention:
searching it yields zero hits for "0-based", "1-based", "index", "chi so",
"danh so". The JSON schema only declares ``correct_option: integer``. The 0..3
range and the ``answer == options[correct_option]`` equality appear ONLY in the
``local_validation`` block, i.e. on the validator side, never in the instruction
sent to the model.

So the model was asked for an unqualified integer, chose the natural human
convention, and was failed by a gate that silently assumed the other one. That is
a specification defect in our instrument.

WHAT THIS MODULE CHANGES: the prompt text only.
WHAT IT DELIBERATELY DOES NOT CHANGE: the deterministic gate. ``correct_option``
must still be an integer in 0..3 and ``answer`` must still equal
``options[correct_option]`` byte-for-byte. Relaxing the gate to also accept
1-based indices after having observed that most attempts used them would be
post-hoc gate loosening; it is also undecidable whenever ``answer`` matches both
``options[co]`` and ``options[co - 1]``.

Two residual genuine model errors seen in round 2c are addressed by instruction
only, never by repair: some responses leaked the literal field name
``"text_evidence_quote"`` into the ``options`` array, and several answered with a
bare letter label ("A"/"B") while the options themselves carried "A: "/"B. "
prefixes.
"""
from __future__ import annotations

# Superseded round-2/2c clarification, retained for provenance and diffing.
from .round2_validation import PROMPT_CLARIFICATION as PROMPT_CLARIFICATION_V1

PROMPT_CLARIFICATION_V2 = (
    "\n\nQUY ƯỚC ĐẦU RA (bắt buộc, đọc kỹ):\n"
    "1. text_evidence_quote phải là một chuỗi con NGUYÊN VĂN của VĂN BẢN NGUỒN "
    "(kênh văn bản ở trên). Không được trích chữ chỉ xuất hiện trong ảnh "
    "(nhãn sơ đồ, chú thích hình, chữ trong bảng ảnh). Nếu chi tiết chỉ thấy "
    "trong ảnh, hãy mô tả nó trong visual_evidence.description, còn "
    "text_evidence_quote vẫn phải lấy từ văn bản nguồn.\n"
    "2. Chỉ với multiple_choice:\n"
    "   - options gồm ĐÚNG 4 chuỗi khác nhau, không rỗng.\n"
    "   - KHÔNG thêm tiền tố thứ tự vào options: không dùng \"A.\", \"B)\", "
    "\"(1)\", \"1-\" ở đầu mỗi lựa chọn. Chỉ ghi nội dung lựa chọn.\n"
    "   - correct_option là CHỈ SỐ ĐÁNH SỐ TỪ 0: 0 là lựa chọn thứ nhất, "
    "1 là thứ hai, 2 là thứ ba, 3 là thứ tư. Chỉ nhận giá trị 0, 1, 2 hoặc 3.\n"
    "   - answer phải CHÉP LẠI NGUYÊN VĂN toàn bộ chuỗi của "
    "options[correct_option], giống từng ký tự. Không được ghi nhãn chữ cái "
    "(\"A\", \"B\", \"C\", \"D\"), không ghi số thứ tự, không viết tắt, không "
    "rút gọn.\n"
    "   - Tự kiểm trước khi trả: answer có bằng đúng options[correct_option] "
    "không, với correct_option đếm từ 0?\n"
    "3. Không bao giờ đưa TÊN TRƯỜNG vào giá trị. Ví dụ chuỗi "
    "\"text_evidence_quote\" không được xuất hiện như một lựa chọn trong options.\n"
    "4. Chỉ trả một JSON object đúng schema, không kèm văn xuôi."
)


def amend_generation_payload(payload: dict, clarification: str = PROMPT_CLARIFICATION_V2) -> dict:
    """Append the clarification to the user text part of a generation payload.

    The payload structure is produced by ``build_generation_request``; the first
    content part of the user message is the text block.
    """
    payload["messages"][1]["content"][0]["text"] += clarification
    return payload


__all__ = [
    "PROMPT_CLARIFICATION_V1",
    "PROMPT_CLARIFICATION_V2",
    "amend_generation_payload",
]
