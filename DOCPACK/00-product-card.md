---
title: Book Grounded AI Assistant — Product Card
doc_id: CARD-book-grounded-ai-assistant
doc_type: product-card
verdict: template
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Book Grounded AI Assistant — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

เป็นแม่แบบอ้างอิงของ `ai-assistant-copilot` ที่ตอบคำถามหนึ่งข้อจาก knowledge set ที่อนุมัติ พร้อม citation หรือคืน fallback โดยไม่เดา

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: AI assistant มักตอบเกินหลักฐานและรั่วข้อมูล; ต้องการโครงที่มี guardrail, redaction และ evaluation ทำซ้ำได้
- ผู้ใช้: นักพัฒนา/agent ที่สร้าง assistant ใหม่ — ไม่ใช่ผู้ใช้ปลายทาง

## 3. สิ่งที่ทำได้จริงตอนนี้

- pipeline: ตรวจ input budget → redact credential/contact → retrieve แบบ deterministic → ตอบพร้อม source หรือ fallback
- adapter `deterministic-extractive-v1` (ไม่มี LLM จริง), `make evaluate` กับ `golden_questions.v1.json`
- CLI `ask` และ HTTP API ที่ใช้ token runtime; telemetry เก็บเฉพาะ hash/outcome/source ids

## 4. หลักฐานสถานะ

| รายการ | ค่า (ตรวจจาก repository) |
|---|---|
| Stack | Python |
| Commits | 9 (แรก 2026-09-09 → ล่าสุด 2026-10-01) |
| Source | 15 ไฟล์ / 1,984 บรรทัด |
| Tests | 3 ไฟล์ |
| CI | 1 workflow |
| Deploy config | ไม่มี |
| Live URL | ไม่มี |
| README | 101 บรรทัด (`book-grounded-ai-assistant`) |
| โครงสร้างซ้ำ (template family) | 2 repo ที่มี structure signature เดียวกัน |

มี structure signature เดียวกับ `book-data-api`

## 5. คุณค่าและจุดต่าง

- คุณค่าคือรูปแบบ guardrail + evaluation ที่นำไปใช้กับ assistant จริงได้
- ไม่มีมุมรายได้ทางตรง; อาจเป็นตัวอย่างประกอบการขายงาน AI ให้ลูกค้า **[สมมติฐาน]**

## 6. ช่องว่างสำคัญ

- ไม่มี model จริง จึงยังไม่พิสูจน์คุณภาพคำตอบกับ LLM
- corpus เป็น fixture เล็ก ไม่มีผู้ใช้

## 7. คำตัดสิน

**`template`** — เป็น reference/starter ไม่ใช่ผลิตภัณฑ์ จะมีค่ามากขึ้นถ้าต่อ adapter ผ่าน Central AI Gateway และใช้กับ knowledge set จริงหนึ่งชุด (เช่น เอกสาร docpack ของลูกค้า)

## 8. ขั้นต่อไป

1. ติด label template
2. ถ้าจะต่อยอด: เพิ่ม adapter ผ่าน AI Gateway โดยคง evaluation gate เดิม

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอพิจารณา | — | ________ |

## แหล่งข้อมูล

- `README.md`
- `PRODUCT.md`
- `src/book_grounded_ai/assistant.py`
- `src/book_grounded_ai/guardrails.py`
- `data/evaluation/golden_questions.v1.json`
