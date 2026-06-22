# Phase 2 Testing Instructions

---

## Files Created

| File | Responsibility |
|------|---------------|
| `app/models/webhook.py` | Pydantic models for inbound payload and response |
| `app/services/tenant_service.py` | Lookup tenant by `phone_number_id` |
| `app/services/session_service.py` | Find active session or create new one with status `waiting_for_bot` |
| `app/services/message_service.py` | Save customer message + update session metadata atomically |
| `app/api/webhook.py` | `POST /api/v1/webhook` (main flow) + `GET /api/v1/webhook` (verification) |
| `tests/test_webhook.py` | Integration tests for all webhook paths |

---

## Step 1: Start the server

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Verify:** `http://localhost:8000/docs` shows 12 endpoints (10 from Phase 1 + 2 new webhook endpoints).

---

## Step 2: Test GET endpoint

```bash
curl http://localhost:8000/api/v1/webhook
```

**Expected:**
```json
{"status": "webhook-ready"}
```

---

## Step 3: Test POST — Furniture Store

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number_id": "123456789",
    "customer_phone": "+919876543210",
    "message": "Send catalog"
  }'
```

**Expected:**
```json
{
  "success": true,
  "tenant": "Furniture Store",
  "session_id": "uuid-string",
  "message_id": "uuid-string"
}
```

---

## Step 4: Test POST — Car Service Center

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number_id": "987654321",
    "customer_phone": "+919876543210",
    "message": "Book oil change"
  }'
```

**Expected:** `"tenant": "Car Service Center"` with a new `session_id`.

---

## Step 5: Test POST — same customer gets existing session

Send the Furniture Store request again:
```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number_id": "123456789",
    "customer_phone": "+919876543210",
    "message": "What is the price?"
  }'
```

**Expected:** Same `session_id` as Step 3. The session service found the active session and reused it.

---

## Step 6: Test POST — unknown tenant (404)

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number_id": "unknown",
    "customer_phone": "+919876543210",
    "message": "Hello"
  }'
```

**Expected:** HTTP 404 with error detail.

---

## Step 7: Test POST — invalid payload (422)

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected:** HTTP 422 with validation errors.

---

## Step 8: Verify in MongoDB

```bash
docker exec -it mongodb mongosh whatsapp_saas
```

```javascript
// Check messages were stored
db.messages.countDocuments({})
// → should be > 0

// View all messages
db.messages.find({}, {
  tenant_id: 1,
  role: 1,
  "content.text": 1,
  created_at: 1
}).pretty()

// Check sessions were created
db.chat_sessions.countDocuments({})
// → should be > 0

// Check session status and message count
db.chat_sessions.find({}, {
  customer_wa_id: 1,
  status: 1,
  message_count: 1,
  last_message_preview: 1
}).pretty()

// Verify tenant lookup works
db.tenants.find(
  { "whatsapp.phone_number_id": "123456789" },
  { name: 1 }
)
// → Furniture Store
```

---

## Step 9: Run automated tests

```bash
pip install pytest httpx pytest-asyncio
pytest tests/ -v
```

**Expected:**
```
tests/test_health.py::test_health_endpoint PASSED
tests/test_webhook.py::test_webhook_get PASSED
tests/test_webhook.py::test_webhook_post_success PASSED
tests/test_webhook.py::test_webhook_post_unknown_tenant PASSED
tests/test_webhook.py::test_webhook_post_invalid_payload PASSED
```

---

## Success Criteria

All six conditions must be true:

- [ ] `GET /api/v1/webhook` returns `{"status": "webhook-ready"}`
- [ ] `POST /api/v1/webhook` with valid payload returns `200` with `success: true`
- [ ] Response includes `tenant` name matching the `phone_number_id`
- [ ] Response includes a valid `session_id` (UUID string)
- [ ] Same customer + tenant returns same `session_id` on second call
- [ ] Messages and sessions are stored in MongoDB with correct data

---

## Architecture Flow (Verified)

```
POST /api/v1/webhook
    │
    ▼
Validate payload (Pydantic)
    │
    ▼
tenant_service.get_tenant_by_phone_number_id("123456789")
    │  → MongoDB: tenants.find({"whatsapp.phone_number_id": "123456789"})
    ▼
session_service.get_or_create_session(tenant_id, customer_wa_id)
    │  → MongoDB: chat_sessions.find({"tenant_id": ..., "customer_wa_id": ..., "status": {"$in": ["active", "waiting_for_bot"]}})
    │  → If not found: insert new session with status "waiting_for_bot"
    ▼
message_service.save_customer_message(tenant_id, session_id, text)
    │  → MongoDB: messages.insert_one({role: "customer", content: {text: "..."}})
    │  → MongoDB: chat_sessions.update_one({$set: {last_message_at, last_message_preview}, $inc: {message_count}})
    ▼
Return 200 {success: true, tenant: "Furniture Store", session_id, message_id}
```
