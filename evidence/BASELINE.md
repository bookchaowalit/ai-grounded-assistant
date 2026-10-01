# Local baseline evidence

สถานะ: `verified-local`

## Scope

หลักฐานนี้ครอบคลุมเฉพาะ local scaffold ของ `book-grounded-ai-assistant` และ
vertical slice `answer-one-grounded-question` ไม่ใช่ hosted model, production
RAG, deployment, cost/SLO หรือ security certification

## Commands

```bash
make test
make check
make evaluate
make demo
```

## Observed result

- `make test`: ผ่าน 37 tests (รวม `tests/test_guardrails.py`) — pass 3
- `make check`: compile และ corpus `validate` ผ่าน
- `make evaluate`: golden questions 17/17 ผ่าน (100%) บน corpus 5 records รวม prompt-injection 6 cases (ภาษาไทย 2); precision/recall ต่อ outcome = 1.0; safety gates (`refused` recall, `grounded` precision) ผ่าน
- `make demo`: known question คืน grounded answer พร้อม citation
- HTTP smoke tests: ask contract และ unauthorized response ผ่าน
- tampered manifest: fail closed
- telemetry inspection: ไม่พบ raw question, raw answer หรือ secret-shaped value

## Reproducibility boundary

corpus และ evaluation set เป็น sanitized public-demo fixture ที่อยู่ใน local
repository ย่อย ไม่มี external network, provider credential, write side effect
หรือ raw private payload ระหว่างการตรวจสอบ

