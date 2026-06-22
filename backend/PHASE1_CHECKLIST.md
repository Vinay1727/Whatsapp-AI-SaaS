# Phase 1 Implementation Checklist

> Estimated time: 2-3 hours
> Goal: FastAPI + MongoDB foundation with tenant data seeded

---

## 1. Create folder structure

```bash
mkdir -p backend/app/api backend/app/core backend/app/db backend/app/models backend/app/services backend/tests backend/migrations
```

**Expected output:** All directories exist.
**Verify:** `ls -R backend/app/` shows `api/ core/ db/ models/ services/`
**Common mistake:** Forgetting `__init__.py` files (already included in this repo).

---

## 2. Create virtual environment

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Linux/Mac
# or
venv\Scripts\activate      # Windows
```

**Expected output:** `(venv)` prefix in terminal prompt.
**Verify:** `which python` points to `backend/venv/bin/python`
**Common mistake:** Forgetting to activate the venv before installing packages.

---

## 3. Install packages

```bash
pip install -r requirements.txt
```

**Expected output:** fastapi, uvicorn, motor, pydantic, pydantic-settings, python-dotenv, python-multipart installed.
**Verify:** `pip list | grep -E "fastapi|uvicorn|motor|pydantic"` shows all 5 packages.
**Common mistake:** Installing globally instead of inside venv.

---

## 4. Start MongoDB

Using Docker:
```bash
docker run -d --name mongodb -p 27017:27017 mongo:7
```

Or use MongoDB Atlas connection string in `.env`.

**Expected output:** MongoDB running on port 27017.
**Verify:** `curl localhost:27017` returns `It looks like you are trying to access MongoDB over HTTP...`
**Common mistake:** Port conflict if another MongoDB instance is running.

---

## 5. Start FastAPI

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**Verify:** Open `http://localhost:8000/docs` — you should see Swagger UI with 6 endpoints.
**Verify:** `curl http://localhost:8000/health` returns `{"status":"ok","database":"connected"}`
**Common mistake:** Running from wrong directory — must be in `backend/`.

---

## 6. Create indexes

```bash
cd backend
python -m migrations.create_indexes
```

**Expected output:** `All indexes created successfully.`
**Verify:** Connect to MongoDB and check indexes:
```bash
docker exec -it mongodb mongosh whatsapp_saas
db.tenants.getIndexes()
```
Should show: `_id_`, `tenant_id_1`, `slug_1`, `whatsapp.phone_number_id_1`
**Common mistake:** Running before MongoDB is connected (script will hang/error).

---

## 7. Seed tenants

```bash
cd backend
python -m migrations.seed_tenants
```

**Expected output:** 
```
  Created: Furniture Store (furniture-store)
  Created: Car Service Center (car-service-center)
  Created: Mobile Store (mobile-store)

Seeded 3 tenants.
```

**Verify:** 
```bash
curl http://localhost:8000/api/v1/tenants
```
Should return 3 tenants.
**Verify:**
```bash
curl http://localhost:8000/api/v1/tenants/lookup/123456789
```
Should return Furniture Store with full config.
**Common mistake:** Running twice without upsert — our script uses `$setOnInsert` so it's idempotent.

---

## 8. Run tests

```bash
pip install pytest httpx pytest-asyncio
pytest tests/ -v
```

**Expected output:**
```
tests/test_health.py::test_health_endpoint PASSED
```

**Verify:** All tests pass (1 test for now).
**Common mistake:** Test may fail if MongoDB is not running (health check will show `degraded`).

---

## 9. Verify MongoDB data

```bash
docker exec -it mongodb mongosh whatsapp_saas
```

Then run:
```javascript
db.tenants.countDocuments()
// → 3

db.tenants.find({}, {name: 1, "whatsapp.phone_number_id": 1})
// → Furniture Store (123456789)
// → Car Service Center (987654321)
// → Mobile Store (5551234567)

db.chat_sessions.countDocuments()
// → 0 (no sessions yet — expected)

db.messages.countDocuments()
// → 0 (no messages yet — expected)
```

**Expected output:** 3 tenants, 0 sessions, 0 messages.
**Common mistake:** Data in wrong database — check `MONGODB_DB_NAME` in `.env`.

---

## VERIFIED — Phase 1 Complete

Signs that Phase 1 is done:
- [ ] `GET /health` returns `200 {"status": "ok", "database": "connected"}`
- [ ] `GET /api/v1/tenants` returns 3 tenants
- [ ] `GET /api/v1/tenants/lookup/123456789` returns Furniture Store
- [ ] `GET /api/v1/tenants/lookup/987654321` returns Car Service Center
- [ ] `GET /api/v1/tenants/lookup/5551234567` returns Mobile Store
- [ ] `POST /api/v1/tenants` creates a new tenant
- [ ] All 3 MongoDB collections exist with proper indexes
- [ ] API docs render at `/docs`

---

## STOP HERE

**Do NOT build any of the following yet:**

| Component | Why not now |
|-----------|-------------|
| **Redis** | Not needed until rate limiting + caching (Phase 3-4) |
| **Celery** | Not needed until webhook volume exceeds BackgroundTasks capacity (Phase 4) |
| **Dashboard** | Frontend is separate phase (Phase 6) |
| **LangGraph** | Requires webhook + message pipeline first (Phase 5) |
| **OpenAI integration** | Requires LangGraph workflow (Phase 5) |
| **WhatsApp webhook integration** | Requires Meta app review + webhook verification (Phase 3) |
| **Vector database** | Not needed until RAG / semantic search (future) |
| **Broadcast campaigns** | Not needed until core messaging works (Phase 6) |
| **Auth0 / RBAC** | Not needed for MVP API assessment (Phase 2) |
| **WebSockets** | Not needed until dashboard real-time (Phase 6) |
| **Media upload to WhatsApp** | Requires WhatsApp API integration (Phase 3) |

**What files exist right now and what they do:**

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, lifespan, health check, CORS
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings from .env
│   │   └── exceptions.py        # Custom exception classes
│   ├── db/
│   │   ├── __init__.py
│   │   └── mongodb.py           # Motor client singleton, get_db dependency
│   ├── api/
│   │   ├── __init__.py
│   │   ├── tenants.py           # CRUD + lookup endpoints
│   │   ├── sessions.py          # Chat session list + detail
│   │   └── messages.py          # Message list + detail
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py            # Tenant, WhatsAppConfig, AIConfig, MediaItem
│   │   ├── chat.py              # ChatSession, EscalationInfo
│   │   └── message.py           # Message, MessageContent
│   └── services/
│       └── __init__.py
├── migrations/
│   ├── __init__.py
│   ├── create_indexes.py        # Idempotent index creation
│   └── seed_tenants.py          # 3 sample tenants with full config
├── tests/
│   ├── __init__.py
│   └── test_health.py           # Basic health check test
├── .env                         # Local environment variables
├── .env.example                 # Template for env vars
├── requirements.txt             # Minimal package deps
└── PHASE1_CHECKLIST.md          # This file
```

**API Endpoints live right now:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check with DB status |
| GET | `/api/v1/tenants` | List all active tenants |
| GET | `/api/v1/tenants/{id}` | Get tenant by tenant_id |
| GET | `/api/v1/tenants/lookup/{phone_number_id}` | Lookup tenant by WhatsApp phone ID |
| POST | `/api/v1/tenants` | Create a new tenant |
| PUT | `/api/v1/tenants/{id}` | Update tenant fields |
| GET | `/api/v1/sessions` | List sessions (filter by tenant_id, status) |
| GET | `/api/v1/sessions/{id}` | Get session by session_id |
| GET | `/api/v1/messages` | List messages for a session_id |
| GET | `/api/v1/messages/{id}` | Get message by message_id |

---

## Next Phase Preview (Phase 2 — only when instructed)

Phase 2 will add:
- WhatsApp webhook endpoint (`POST /webhook`)
- X-Hub-Signature-256 validation
- Message persistence from incoming webhooks
- Chat session auto-creation on first message
- Webhook verification challenge (`GET /webhook`)
- Background task processing
