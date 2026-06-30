# LLM Judge Bias Report — Phase B

**Sinh viên:** Nguyễn Đức Thanh (2A202600838)
**Ngày:** 2026-07-01
**Judge model:** `gemini-2.5-flash` (Google Gemini qua OpenAI-compatible endpoint, không phải gpt-4o-mini)

---

## 1. Pairwise Judge Results

*(`pairwise_judge()` chạy trên 10 cặp: A = model_answer thực tế từ Day 18 pipeline, B = ground_truth.
Đây cũng là 10 câu trong `human_labels_10q.json` dùng cho Cohen's κ ở mục 3.)*

| # | Question (tóm tắt) | Winner | Reasoning tóm tắt |
|---|---|---|---|
| 1 | Nghỉ bao nhiêu ngày khi kết hôn? | B | model_answer đúng nhưng B (ground truth) được judge cho súc tích/chuẩn hơn |
| 2 | Mua thiết bị 55 triệu cần ai phê duyệt? | B | model_answer thiếu — chỉ nói Trưởng phòng, ground truth có đủ ngưỡng phê duyệt CEO |
| 3 | Thưởng Tết tối thiểu 6 tháng+ | B | cả hai đúng nội dung, judge nghiêng về B vì là tham chiếu chuẩn |
| 4 | Senior 9 năm: phép năm + lương | B | model_answer tính đúng nhưng judge vẫn chọn ground truth khi so kè trực tiếp |
| 5 | Tài trợ khóa học 25tr, nghỉ sau 8 tháng — hoàn trả? | B | model_answer đúng (100% hoàn trả) nhưng vẫn thua B trong so sánh trực diện |
| 6 | Tạm ứng 8tr, quá hạn 30 ngày — phê duyệt + phạt? | tie (swap không nhất quán) | Pass 1: A thắng, Pass 2: B thắng → position bias, final = tie |
| 7 | Manager 12 năm: phụ cấp + phép năm | B | model_answer đúng cả hai số liệu, vẫn thua B |
| 8 | Nghỉ phép năm bao nhiêu ngày? | B | model_answer trả lời theo policy cũ (v2023, 12 ngày) — B đúng (v2024, 15 ngày) |
| 9 | Thử việc có nghỉ phép năm không? | **A** | model_answer đúng và đầy đủ — đây là 1/10 case model_answer thắng |
| 10 | Manager dùng VPN cá nhân khi WFH? | B | model_answer sai (nói "được") — B đúng (cấm VPN cá nhân) |

---

## 2. Swap-and-Average Results

| # | Pass 1 Winner | Pass 2 Winner | Final | Position Consistent? |
|---|---|---|---|---|
| 1 | B | B | B | True |
| 2 | B | B | B | True |
| 3 | B | B | B | True |
| 4 | B | B | B | True |
| 5 | B | B | B | True |
| 6 | A | B | **tie** | **False** |
| 7 | B | B | B | True |
| 8 | B | B | B | True |
| 9 | A | A | A | True |
| 10 | B | B | B | True |

**Position bias rate:** 10% (1/10 case — câu #6, tạm ứng/phạt — đổi kết quả khi swap thứ tự A/B)

---

## 3. Cohen's κ Analysis

**Human labels:** `human_labels_10q.json` (10 câu, 6 label=1 đúng, 4 label=0 sai)
**Judge labels:** `judge_labels[i] = 1` nếu `final_winner ∈ {A, tie}` (model_answer được judge coi là chấp
nhận được khi so với ground truth), `= 0` nếu `final_winner = B` (ground truth thắng rõ ràng)

| Question ID | Human Label | Judge Label | Agree? |
|---|---|---|---|
| 1 | 1 | 0 | ✗ |
| 5 | 0 | 0 | ✓ |
| 12 | 1 | 0 | ✗ |
| 21 | 1 | 0 | ✗ |
| 23 | 1 | 0 | ✗ |
| 29 | 0 | 1 (tie) | ✗ |
| 33 | 1 | 0 | ✗ |
| 41 | 0 | 0 | ✓ |
| 46 | 1 | 1 | ✓ |
| 50 | 0 | 0 | ✓ |

**Cohen's κ:** **-0.0714**
**Interpretation:** poor (< 0) — judge và human gần như KHÔNG đồng thuận, tệ hơn cả random chance.

---

## 4. Verbosity Bias

Trong 9/10 case có winner rõ ràng (không phải tie):
- A thắng + A dài hơn B: **0 / 9** cases
- B thắng + B dài hơn A: **8 / 9** cases
- **Verbosity bias rate:** 88.9%

**Kết luận:** Đây KHÔNG phải verbosity bias theo nghĩa cổ điển "LLM thiên vị câu dài dù sai" — ở đây B
(ground_truth) vừa dài/chi tiết hơn VÀ đúng hơn về nội dung, nên judge chọn B vì lý do chính đáng (chính
xác), độ dài chỉ là tương quan đi kèm. Tuy vậy số liệu 88.9% vẫn đáng lưu ý: judge có thể đang dùng "độ
đầy đủ thông tin" làm tín hiệu thay thế cho "độ chính xác" khi không chắc — đây là rủi ro thật trong
production nếu answer dài nhưng sai vẫn được ưu tiên.

---

## 5. Nhận xét chung

> **κ chưa đạt 0.6** (κ=-0.071, "poor") — root cause không phải do judge "tệ" theo nghĩa thường, mà do
> **thiết kế phương pháp đo**: so sánh pairwise model_answer vs ground_truth gần như luôn cho ground_truth
> thắng (vì nó LÀ đáp án chuẩn), trong khi nhãn nhân (`human_label`) đang chấm theo tiêu chí "model_answer
> có đủ chấp nhận được không" — hai tiêu chí khác nhau về bản chất. Ví dụ rõ nhất: câu #1, #12, #21, #23,
> #33 đều có model_answer ĐÚNG (human_label=1) nhưng judge vẫn chọn B vì ground_truth súc tích/chuẩn hơn
> trong so sánh trực diện. → **κ thấp ở đây phản ánh sai lệch phương pháp đo, không phải judge thiếu tin
> cậy về mặt factual.**
>
> **Position bias 10%** (1/10) là mức thấp, judge khá ổn định khi đổi thứ tự A/B — swap-and-average hoạt
> động đúng như kỳ vọng (phát hiện được đúng 1 case bị ảnh hưởng vị trí).
>
> **Verbosity bias 88.9%** cần theo dõi thêm — tương quan cao giữa "câu dài hơn" và "câu thắng", dù trong
> bộ dữ liệu này độ dài đi kèm với độ chính xác cao hơn (không phải false correlation), nên không kết luận
> được đây là bias thật hay chỉ là correlation hợp lý với cỡ mẫu n=9.
>
> **Khuyến nghị cho production:** không dùng pairwise-vs-ground-truth để đo agreement với human reviewer.
> Thay vào đó: (1) dùng **absolute grading rubric** (chấm 1 câu trả lời độc lập theo thang điểm/đúng-sai
> rõ ràng, có ground_truth làm CONTEXT cho judge tham khảo chứ không phải đối thủ cạnh tranh), giữ lại
> swap-and-average + verbosity check như lớp giám sát bias riêng cho các tác vụ pairwise thật (A/B testing
> giữa 2 phiên bản model).
