# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Nguyễn Đức Thanh (2A202600838)
**Ngày:** 2026-07-01

> **Lưu ý về LLM provider:** Stack này chạy hoàn toàn trên **Google Gemini** (không phải OpenAI thật),
> dù một số config vẫn khai `engine: openai` — đó là vì code trỏ `base_url` sang endpoint
> OpenAI-compatible của Google (`generativelanguage.googleapis.com/v1beta/openai/`) và đọc key qua
> `GOOGLE_API_KEY`. Models dùng: `gemini-2.5-flash-lite` (RAGAS eval + sinh answer),
> `gemini-2.5-flash` (LLM Judge + NeMo Guardrails self-check).

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~15ms P95)
[Presidio PII Scan]
    │ block if: VN_CCCD / VN_PHONE / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~20.8s P95 — xem ghi chú Latency Budget)
[NeMo Self-Check Input Rail]
    │ block if: jailbreak / off-topic / prompt injection / pii request
    │ action:   return 503 + refuse message
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 Search → M3 Rerank → Gemini-2.5-flash-lite
    ▼
[NeMo Self-Check Output Rail]
    │ flag if:  CCCD / SĐT / mật khẩu / thông tin bí mật trong response
    │ action:   replace with safe response
    ▼
User Response
```

---

## Latency Budget

*(Kết quả thực tế từ `measure_p95_latency()`, 10 adversarial inputs)*

| Layer | P50 (ms) | P95 (ms) | P99 (ms) | Budget |
|---|---|---|---|---|
| Presidio PII | 11.79 | 14.98 | 14.98 | <10ms |
| NeMo Self-Check Input Rail | 2679.04 | 20779.06 | 20779.06 | <300ms |
| RAG Pipeline | *(chưa đo riêng — đã có trong `naive_baseline.py`/`setup_answers.py`)* | — | — | <2000ms |
| **Total Guard (Presidio + NeMo)** | 2689.64 | **20790.84** | 20790.84 | **<500ms** |

**Budget OK?** [x] No

**Comment:** NeMo là bottleneck tuyệt đối — vượt budget ~40x. Nguyên nhân root cause: `gemini-2.5-flash`
mặc định bật **"thinking" mode**, model dành phần lớn token budget cho reasoning ẩn trước khi sinh câu
trả lời thật (đo trực tiếp: với `max_tokens=3` model trả về content rỗng hoàn toàn vì hết budget cho
thinking, phải tăng lên `max_tokens=500` để có output ổn định). Cách tối ưu cho production:
(1) đổi sang `gemini-2.5-flash-lite` (không/ít thinking) cho self-check input/output rail,
(2) tắt thinking qua `extra_body: {"thinking_config": {"thinking_budget": 0}}` nếu model hỗ trợ,
(3) cache kết quả self-check cho các câu hỏi lặp lại.

---

## CI/CD Gates (phải pass trước khi merge to main)

```yaml
# .github/workflows/rag_eval.yml
- name: RAGAS Quality Gate
  run: python src/phase_a_ragas.py
  env:
    MIN_FAITHFULNESS: 0.75
    MIN_AVG_SCORE: 0.65

- name: Guardrail Gate
  run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
  # phải ≥ 15/20 (75%)

- name: Latency Gate
  run: python -c "from src.phase_c_guard import measure_p95_latency; ..."
  # P95 total < 500ms
```

**Trạng thái thực tế của 3 gates này với pipeline hiện tại:**
- RAGAS faithfulness ≥0.75 (50q): **0.78** (trung bình 3 distribution: 1.0/0.64/0.70) → **PASS** sát ngưỡng,
  nhưng `multi_hop` riêng lẻ chỉ 0.64 → **FAIL** nếu gate theo từng distribution.
- Adversarial pass rate ≥90% (18/20): **20/20 (100%)** → **PASS**
- P95 total guard latency <500ms: **20790.84ms** → **FAIL** (do NeMo thinking, xem trên)

---

## Monitoring Dashboard (production)

| Metric | Alert Threshold | Action |
|---|---|---|
| RAGAS faithfulness (daily sample) | < 0.70 | Page on-call |
| Adversarial block rate | < 80% | Review new attack patterns |
| Guard P95 latency | > 600ms | Scale NeMo model / tắt thinking |
| PII detected count | spike >10/hour | Security alert |

---

## Kết quả thực tế từ Lab

| | Kết quả |
|---|---|
| RAGAS avg_score (50q, theo distribution) | factual **0.9528** / multi_hop **0.6878** / adversarial **0.8159** |
| Worst metric | `answer_relevancy` (factual), `faithfulness`+`context_precision` (multi_hop) |
| Dominant failure distribution | factual (12/24 worst_metric=answer_relevancy là factual) |
| Cohen's κ (judge vs human) | **-0.071** (poor — gần như không đồng thuận) |
| Adversarial pass rate | **20 / 20** |
| Guard P95 latency | **20790.84 ms** (NeMo self-check là bottleneck) |
| Bonus criteria đạt | 2/3 (pass rate ≥18/20 ✓, adversarial avg < factual avg ✓ — 0.816<0.953; κ>0.6 ✗) |

---

## Nhận xét & Cải tiến

> **Điều hoạt động tốt:** Pipeline xử lý rất tốt câu hỏi `factual` (avg 0.953, faithfulness=1.0) — retrieval
> đơn-tài-liệu + rerank hoạt động đúng như kỳ vọng. Guardrail (Presidio + NeMo self-check) chặn 100%
> (20/20) adversarial inputs sau khi sửa từ pattern "user ask X / bot refuse X" (canonical-form matching,
> không hoạt động đúng trên nemoguardrails 0.22 — luôn match flow đầu tiên bất kể nội dung, 0 LLM call)
> sang pattern chính thức `self check input/output` (1 LLM call duy nhất, prompt rõ ràng).
>
> **Điều cần cải thiện:** `multi_hop` là điểm yếu rõ rệt (avg 0.688, context_precision chỉ 0.509) — pipeline
> Day 18 chưa đủ tốt để kết hợp nhiều tài liệu cho tính toán (lương, phép tích lũy, phụ cấp). Cohen's κ âm
> cho thấy LLM-judge khi so sánh model_answer trực diện với ground_truth là một bài kiểm tra QUÁ NGHIÊM
> (ground_truth gần như luôn "thắng" vì là tham chiếu chuẩn) — không phản ánh đúng "đủ tốt" theo human
> rater; nên dùng absolute grading rubric (chấm 1 câu trả lời độc lập theo rubric, không so kè với đáp án
> mẫu) khi muốn đo lường đồng thuận với nhãn nhân. Latency NeMo vượt budget 40x do thinking mode của
> gemini-2.5-flash — cần đổi model hoặc tắt thinking cho production.
>
> **Nếu deploy production thực sự**, tôi sẽ: (1) đổi guard LLM sang model không-thinking (flash-lite) hoặc
> set `thinking_budget=0`, (2) thêm BM25/metadata filter riêng cho multi-hop tính toán, (3) thay κ-based
> judge bằng rubric tuyệt đối + vẫn giữ swap-and-average để theo dõi position bias, (4) thêm circuit breaker
> + cache cho RAGAS evaluation để giảm phụ thuộc vào rate limit free-tier của Gemini.
