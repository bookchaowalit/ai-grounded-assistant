# Architecture — book-grounded-ai-assistant

## Flow

1. `data/landing/knowledge_sources.json` เก็บ approved sanitized source snapshot
2. `data/bronze/knowledge_chunks.v1.json` เก็บ versioned corpus projection
3. manifest ผูก source/Bronze object ด้วย path, SHA-256, schema, privacy,
   retention และ record count
4. `store.load_corpus()` fail closed หาก object, hash, schema, path หรือ parity
   ไม่ถูกต้อง
5. `redaction.redact_question()` ลด credential/contact-shaped input ก่อน
   retrieval และไม่เผยค่าที่ match
6. deterministic retriever ใช้ bounded lexical overlap (`top_k=1`, minimum
   score 2) เป็น local reference adapter
7. assistant คืน `answer.v1` แบบ grounded หรือ `insufficient-context` fallback
   แล้วส่ง safe telemetry เข้า in-memory sink
8. HTTP/CLI เป็น consumer boundary; ไม่มี write ไป repository อื่นหรือ external
   system

## AI decision contract

| มิติ | baseline decision |
| --- | --- |
| Model/provider | `deterministic-extractive-v1`; ไม่มี provider call |
| Context budget | คำถามสูงสุด 500 chars; retrieve 1 source; source text สูงสุด 4,000 chars |
| Output budget | คำตอบสูงสุด 2,000 chars |
| Fallback | ถ้า overlap ต่ำกว่า 2 ให้ตอบ insufficient-context และไม่เดา |
| Evaluation | golden set 3 cases; required pass rate 100% |
| Redaction | bearer token, API key/token/secret assignments และ email |
| Latency target | local reference target `<100ms`; วัดใน telemetry แต่ยังไม่ใช่ SLO |
| Rollback | คืน corpus snapshot/manifest ที่ผ่าน hash แล้วรัน `make test` ใหม่ |

## Trust and privacy boundaries

- corpus classification คือ `public-demo`; fixture URLs ใช้ `example.invalid`
- request body ต้องเป็น JSON object ที่มี field `question` เพียง field เดียว
- server bind default เป็น `127.0.0.1`; หากไม่มี token ต้องใช้ explicit
  `--allow-unauthenticated-local`
- error response ไม่ echo question หรือ raw payload
- telemetry เก็บ hash ของ redacted question/answer, source ids, outcome และ
  latency เท่านั้น; ไม่มี raw prompt, raw response หรือ secret value
- assistant ไม่สร้าง external action และไม่มี adapter สำหรับ remote model ใน
  baseline นี้

## Verification and gaps

local tests ครอบคลุม known/unknown question, citation, input budget, redaction,
manifest tamper, source/Bronze contract, auth, malformed body, rate limit,
HTTP server และ CLI evaluation

ยังเป็น gap ก่อน production: real Parquet/Object Storage, vector retrieval,
provider/model adapter, prompt injection evaluation, model quality benchmark,
cost accounting, distributed rate limit, persistent telemetry, access review,
deletion/retention automation และ owner-approved release record

