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

- `make test`: ผ่าน 13 tests
- `make check`: compile และ corpus `validate` ผ่าน
- `make evaluate`: golden questions 3/3 ผ่าน (100%)
- `make demo`: known question คืน grounded answer พร้อม citation
- HTTP smoke tests: ask contract และ unauthorized response ผ่าน
- tampered manifest: fail closed
- telemetry inspection: ไม่พบ raw question, raw answer หรือ secret-shaped value

## Reproducibility boundary

corpus และ evaluation set เป็น sanitized public-demo fixture ที่อยู่ใน local
repository ย่อย ไม่มี external network, provider credential, write side effect
หรือ raw private payload ระหว่างการตรวจสอบ

