# book-grounded-ai-assistant

`book-grounded-ai-assistant` คือ reference implementation ของ
`ai-assistant-copilot` สำหรับ vertical slice `answer-one-grounded-question`

## Purpose

ผู้ใช้ถามคำถามหนึ่งข้อจาก approved knowledge set แล้วระบบจะ:

1. ตรวจ input budget และ redact credential/contact-shaped values
2. retrieve context จาก `knowledge.v1` corpus แบบ deterministic
3. คืนคำตอบที่มี source citation เมื่อ evidence ถึง threshold
4. คืน fallback เมื่อ context ไม่พอ โดยไม่เดาและไม่ทำ external action
5. บันทึกเฉพาะ safe telemetry (hash, outcome, source ids, latency) ใน memory

ไม่มี external model/provider ใน baseline นี้ ตัว adapter คือ
`deterministic-extractive-v1` เพื่อให้ contract, fallback, redaction และ
evaluation ทำซ้ำได้โดยไม่ใช้ credential

## Data flow

```text
data/landing/knowledge_sources.json
        │
        ├── data/manifests/knowledge_chunks.v1.manifest.json
        │
        ▼
data/bronze/knowledge_chunks.v1.json
        │
        ▼
redact → retrieve → grounded answer / safe fallback
```

ทุกครั้งที่โหลด corpus ระบบตรวจ SHA-256, schema, privacy class, record count,
path boundary และ source/Bronze parity ก่อนให้ assistant อ่านข้อมูล

## Run locally

```bash
make test
make check
make evaluate
make demo
```

ถามผ่าน CLI:

```bash
PYTHONPATH=src python3 -m book_grounded_ai.cli ask \
  --question "Where should approved source evidence live?" --json
```

เปิด HTTP API โดยสร้าง token เฉพาะ runtime ใน shell:

```bash
export BOOK_GROUNDED_AI_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
PYTHONPATH=src python3 -m book_grounded_ai.cli serve --port 8090
```

อนุญาต server แบบไม่มี token ได้เฉพาะ local development ที่ระบุ flag นี้
อย่างชัดเจน:

```bash
PYTHONPATH=src python3 -m book_grounded_ai.cli serve \
  --allow-unauthenticated-local --port 8090
```

เรียก API:

```bash
curl http://127.0.0.1:8090/healthz
curl -H "Authorization: Bearer $BOOK_GROUNDED_AI_TOKEN" \
  http://127.0.0.1:8090/v1/metadata
curl -X POST \
  -H "Authorization: Bearer $BOOK_GROUNDED_AI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"How should a reference app handle provider changes?"}' \
  http://127.0.0.1:8090/v1/ask
```

## Contract boundary

- `GET /healthz` เป็น public health check และไม่คืน corpus text
- `GET /v1/metadata` แสดง adapter, budget, corpus lineage และ policy
- `POST /v1/ask` รับ JSON ที่มีเพียง `question` และคืน `answer.v1`
- คำถามยาวเกิน 500 ตัวอักษร, body เกิน 8 KiB หรือ schema ไม่ถูกต้องถูกปฏิเสธ
- auth ใช้ Bearer token เมื่อ serve; rate limit เป็น in-memory ต่อ client
- redaction รองรับ bearer token, `api_key`/`token`/`secret` patterns และ email
- telemetry ไม่เก็บ raw question, raw answer หรือ matched secret
- local adapter ไม่มี network, provider call, write API หรือ external action

นี่เป็น local baseline เพื่อพิสูจน์ contract และ role/step acceptance เท่านั้น
ไม่ใช่ hosted LLM, production RAG, model quality certification หรือ cost/SLO
evidence

