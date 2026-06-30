# Failure Cluster Analysis — Phase A

**Sinh viên:** Nguyễn Đức Thanh (2A202600838)
**Ngày:** 2026-07-01
**LLM provider:** Google Gemini (`gemini-2.5-flash-lite` cho sinh answer + RAGAS judge/embeddings, qua
OpenAI-compatible endpoint, không phải OpenAI thật)

---

## 1. Aggregate RAGAS Scores theo Distribution

| Metric | factual | multi_hop | adversarial |
|---|---|---|---|
| faithfulness | 1.0000 | 0.6416 | 0.7000 |
| answer_relevancy | 0.9073 | 0.7118 | 0.9092 |
| context_precision | 0.9417 | 0.5093 | 0.8333 |
| context_recall | 0.9250 | 0.7708 | 0.7167 |
| **avg_score** | **0.9528** | **0.6878** | **0.8159** |

*(1/50 câu — id 2, "Bảo hiểm sức khỏe PVI có hạn mức bao nhiêu cho nhân viên?" — bị NaN ở
`context_precision` sau khi hết retry với Gemini free-tier, dù đã cấu hình `RunConfig(max_workers=3,
max_retries=6)`. Aggregate trên dùng nanmean (bỏ qua câu lỗi), nên không bị lệch số.)*

---

## 2. Bottom 10 Questions

| Rank | Distribution | Question | avg_score | worst_metric |
|---|---|---|---|---|
| 1 | factual | Nhân viên được nghỉ bao nhiêu ngày khi kết hôn? | 0.9987† | answer_relevancy |
| 2 | factual | Bảo hiểm sức khỏe PVI có hạn mức bao nhiêu cho nhân viên? | NaN‡ | context_precision |
| 3 | multi_hop | Một nhân viên Senior có 9 năm thâm niên được nghỉ bao nhiêu ngày phép năm và lương trong khoảng nào? | 0.2500 | answer_relevancy / faithfulness |
| 4 | multi_hop | So sánh yêu cầu mật khẩu giữa policy v1.0 và v2.0 | 0.2500 | answer_relevancy |
| 5 | multi_hop | Nhân viên Manager có thâm niên 12 năm: tổng phụ cấp hàng tháng và số ngày phép năm? | 0.3393 | answer_relevancy |
| 6 | multi_hop | Nhân viên tạm ứng 15 triệu, sau 20 ngày mới thanh toán... | 0.5000 | faithfulness |
| 7 | multi_hop | Nhân viên thử việc tháng thứ 3 phát hiện vi phạm bảo mật... | 0.5742 | faithfulness |
| 8 | multi_hop | So sánh quyền lợi bảo hiểm giữa nhân viên thử việc và chính thức | 0.5921 | context_precision |
| 9 | adversarial | Bao lâu phải đổi mật khẩu một lần? | 0.6132 | faithfulness |
| 10 | multi_hop | Nhân viên vừa kết hôn và cùng tuần đó có con kết hôn... | 0.6442 | context_precision |

† Rank #1 thực ra có avg_score rất cao (0.9987) — `bottom_10()` sort tăng dần nhưng do câu #2 bị NaN, thứ
tự sort của Python với NaN không ổn định, khiến #1 (điểm cao) và #2 (NaN) bị xáo trộn lên đầu danh sách
thay vì các câu điểm thấp thật. Các rank #3-10 là chính xác (điểm thấp thật, tăng dần).
‡ Xem ghi chú NaN ở mục 1.

---

## 3. Failure Cluster Matrix

*(Mỗi ô = số câu có worst_metric = row, thuộc distribution = col, trên 50 câu)*

| worst_metric | factual | multi_hop | adversarial | Total |
|---|---|---|---|---|
| faithfulness | 2 | 9 | 3 | 14 |
| answer_relevancy | 12 | 4 | 2 | 18 |
| context_precision | 5 | 6 | 2 | 13 |
| context_recall | 1 | 1 | 3 | 5 |

---

## 4. Dominant Failure Analysis

**Dominant distribution:** factual *(theo số lượng câu có worst_metric thuộc nhóm, không phải vì factual
yếu — factual thực ra có avg_score cao nhất 0.953; "dominant" ở đây phản ánh phân bố worst_metric, không
phải mức độ nghiêm trọng)*
**Dominant metric:** answer_relevancy

**Lý do phân tích:**

> `answer_relevancy` là metric yếu nhất ở nhóm `factual` (12/20 câu) dù faithfulness=1.0 hoàn hảo — nghĩa
> là model trả lời ĐÚNG sự thật (không hallucinate) nhưng câu trả lời không khớp sát với câu hỏi (có thể
> dư thông tin hoặc trả lời lệch ý). Ngược lại, `multi_hop` thất bại chủ yếu ở `faithfulness` (9/20) và
> `context_precision` (6/20) — đây là dấu hiệu rõ của retrieval/reranking chưa đủ tốt để gom đúng các
> tài liệu cần cho phép tính nhiều bước (lương + phép tích lũy theo thâm niên, tổng phụ cấp...), khiến
> model phải "bù" bằng suy luận ngoài context (hallucination) hoặc chỉ tóm tắt sai context không liên quan.

---

## 5. Suggested Fixes

| Metric yếu | Root cause | Suggested fix |
|---|---|---|
| faithfulness | LLM hallucinating khi context không đủ cho phép tính multi-hop | Tighten system prompt ("chỉ tính nếu có đủ dữ liệu trong context"), thêm explicit calculation step |
| context_recall | Missing relevant chunks (rõ nhất ở adversarial: 0.717) | Tăng `RERANK_TOP_K`, thêm BM25 weight cho version-conflict queries |
| context_precision | Multi-hop cần nhiều tài liệu cùng lúc, reranker single-doc-biased | Thêm metadata filter theo loại policy (lương/phép/phụ cấp) trước khi rerank |
| answer_relevancy | factual: answer đúng nhưng lệch ý câu hỏi | Cải thiện prompt template — yêu cầu trả lời thẳng vào câu hỏi, giảm thông tin dư |

---

## 6. Nhận xét về Adversarial Distribution

> Adversarial avg_score (0.8159) thấp hơn factual (0.9528) nhưng **cao hơn** multi_hop (0.6878) — tức bộ
> test set adversarial (version conflict v2023/v2024, negation traps) gây khó cho pipeline nhưng KHÔNG khó
> bằng multi_hop tính toán thực sự. Câu adversarial duy nhất rơi vào bottom 10 là "Bao lâu phải đổi mật
> khẩu một lần?" (rank #9, faithfulness=worst) — đây chính là bẫy version-conflict giữa `mat_khau_v1.md`
> và `mat_khau_v2.md`: pipeline có khả năng trộn lẫn quy định cũ/mới do cả hai tài liệu đều được retrieve
> với độ liên quan cao. Điều này khớp với mục tiêu thiết kế test set — "version conflicts là bẫy pipeline
> hay nhầm nhất" — và xác nhận: cần metadata versioning (date/status field) để lọc tài liệu hết hiệu lực
> trước khi đưa vào context, không chỉ dựa vào similarity search.
