# Product brief — book-grounded-ai-assistant

## Job to be done

ช่วยผู้ใช้ตอบคำถามจาก knowledge set ที่ได้รับอนุมัติ โดยให้ผู้ใช้ตรวจ source
ได้และรู้ทันทีเมื่อ evidence ไม่พอ

## Vertical slice

`answer-one-grounded-question`

หนึ่ง request รับคำถามหนึ่งข้อ ใช้ approved local corpus และ deterministic
adapter เพื่อทดสอบ retrieval, citation, uncertainty, redaction และ fallback
ครบ end-to-end

## Acceptance criteria

| พื้นที่ | เกณฑ์ยอมรับ | หลักฐาน local |
| --- | --- | --- |
| Grounded answer | คำถามที่อยู่ใน corpus ได้ answer พร้อม source citation | `assistant.py`, tests |
| Safe uncertainty | คำถามนอก corpus ได้ fallback และไม่เดา | `test_unknown_question_returns_safe_fallback` |
| Provider-neutral | product contract แยกจาก model/provider และใช้ local adapter ได้ | `config.py`, `ARCHITECTURE.md` |
| Privacy | input redaction และ telemetry ไม่มี raw prompt/answer | `redaction.py`, `telemetry.py`, tests |
| Measured change | golden questions ต้องผ่าน 100% ก่อน baseline ถือว่าผ่าน | `data/evaluation/`, `evaluation.py` |
| Runtime boundary | auth, body limit, rate limit และ no-action path ถูกบังคับ | `api.py`, HTTP tests |

## Non-goals ของ baseline

- ไม่เชื่อม hosted LLM, vector database, external provider หรือ remote gateway
- ไม่ทำ autonomous action, tool call, write endpoint หรือ regulated decision
- ไม่เก็บ raw private prompt/response ใน log, telemetry หรือ fixture
- ไม่อ้าง model quality, production latency, cost หรือ availability SLO
- ไม่แทนที่ corpus owner, privacy review, release approval หรือ runbook จริง

## Ownership boundary

local reference app owner: `product-manager` / `ai-product-delivery` review
โดย owner และ privacy/security approval ยังเป็น gate ก่อน release หรือ provider
integration

