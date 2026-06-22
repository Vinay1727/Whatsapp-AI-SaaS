# WhatsApp AI Support & Sales Agent — System Architecture

> Production-Grade Multi-Tenant SaaS Architecture
> Document Version: 1.0.0

---

## Table of Contents

1. [High-Level Architecture](#step-1-high-level-architecture)
2. [Folder Structure](#step-2-folder-structure)
3. [MongoDB Collections](#step-3-mongodb-collections)
4. [LangGraph Architecture](#step-4-langgraph-architecture)
5. [WhatsApp Integration Layer](#step-5-whatsapp-integration-layer)
6. [Async Processing Architecture](#step-6-async-processing-architecture)
7. [Frontend Dashboard](#step-7-frontend-dashboard)
8. [Security Layer](#step-8-security-layer)
9. [Deployment Architecture](#step-9-deployment-architecture)
10. [Implementation Roadmap](#step-10-implementation-roadmap)

---

## STEP 1: High-Level Architecture

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#1a1a2e', 'primaryTextColor': '#e0e0e0', 'primaryBorderColor': '#4a4a6a', 'lineColor': '#6a6a8a', 'secondaryColor': '#16213e', 'tertiaryColor': '#0f3460'}}}%%

graph TB
    %% External Systems
    subgraph "🌐 External"
        WA[WhatsApp Cloud API]
        CUST[Customer Phone]
    end

    %% Entry Layer
    subgraph "🛡️ Entry & Security Layer"
        LB[Load Balancer]
        WAF[WAF / Rate Limiter]
        WH[Webhook Receiver<br/>FastAPI]
        VAL[Signature Validator<br/>X-Hub-Signature-256]
    end

    %% API Layer
    subgraph "⚡ API Layer"
        API[FastAPI Application]
        MID[Middleware Stack<br/>Auth / Tenant Context / Logging]
        ROUTE1[/webhook<br/>POST]
        ROUTE2[/api/v1/*]
        ROUTE3[/health<br/>GET]
        ROUTE4[/monitor/ws<br/>WebSocket]
    end

    %% Processing Layer
    subgraph "🧠 Processing Layer"
        ACK[Acknowledge Node<br/>Mark Read + Typing]
        CR[Context Retriever<br/>MongoDB + Vector]
        SENT[Sentiment Analyzer]
        LLM[LLM Reasoning<br/>LangGraph]
        DISP[Dispatcher]
        HH[Human Handover<br/>Socket.IO Push]
        MEDIA[Media Processor<br/>Image / Document]
    end

    %% Async Layer
    subgraph "⏳ Async Processing Layer"
        CEL[Task Queue<br/>Celery / Redis]
        WKR[Worker Pool]
        SCHED[Scheduler<br/>Broadcast Campaigns]
    end

    %% Data Layer
    subgraph "🗄️ Data Layer"
        MDB[(MongoDB Atlas<br/>Primary Store)]
        VDB[(Vector Store<br/>MongoDB Atlas Search)]
        CACHE[(Redis Cache<br/>Session / Rate Limit)]
        S3[(Object Storage<br/>Media Files)]
    end

    %% Frontend
    subgraph "📊 Frontend Dashboard"
        FE[Next.js App<br/>Vercel]
        AUTH[Auth0 / JWT]
        DASH[Live Dashboard]
        WS[WebSocket Client]
    end

    %% LangGraph Internal
    subgraph "🔁 LangGraph State Machine"
        direction LR
        START((Start))
        N1[ACK]
        N2[Context]
        N3[Sentiment]
        N4[LLM<br/>Reason]
        N5{Dispatch}
        N6[Human]
        END((End))

        START --> N1
        N1 --> N2
        N2 --> N3
        N3 --> N4
        N4 -->|Auto| N5
        N5 -->|Confidence > 0.8| END
        N5 -->|Confidence < 0.6| N6
        N6 -->|Resolved| END
        N6 -->|Escalate| N5
    end

    %% Data Flow
    CUST -->|Message| WA
    WA -->|Webhook POST| WAF
    WAF --> LB
    LB --> WH
    WH --> VAL
    VAL --> MID
    MID --> ROUTE1
    
    ROUTE1 -->|BackgroundTask| ACK
    ACK --> CEL
    
    CEL --> WKR
    WKR --> CR
    CR --> VDB
    CR --> MDB
    CR --> SENT
    SENT --> LLM
    LLM --> DISP
    DISP -->|Text/Image/Doc| WA
    DISP -->|Low Confidence| HH
    
    %% Dashboard connections
    FE -.->|WebSocket| ROUTE4
    ROUTE4 -.-> MDB
    ROUTE4 -.-> HH

    %% Media flows
    MEDIA -.-> S3
    MEDIA -.-> WA

    %% Styling
    classDef aws fill:#1a1a2e,stroke:#4a4a6a,color:#e0e0e0
    classDef fast fill:#16213e,stroke:#0f3460,color:#e0e0e0
    classDef graph fill:#0f3460,stroke:#1a1a2e,color:#e0e0e0
    class WA,CUST aws
    class WH,API,MID,ROUTE1,ROUTE2,ROUTE3,ROUTE4 fast
    class N1,N2,N3,N4,N5,N6 graph
```

### Data Flow Summary

```
1. Customer sends WhatsApp message
2. WhatsApp Cloud API → POST webhook to our endpoint
3. FastAPI validates X-Hub-Signature-256
4. Tenant resolved from phone_number_id
5. 200 OK returned immediately (< 3s)
6. Background task enqueued to Celery
7. Celery worker runs LangGraph workflow:
   a. Acknowledge: Mark as read + typing indicator
   b. Context: Retrieve conversation history + tenant config
   c. Sentiment: Analyze customer sentiment
   d. LLM Reason: Generate response using tenant-specific prompt
   e. Dispatch: Send text/image/document via WhatsApp API
   f. Handover: If low confidence, notify human agent
8. All state persisted to MongoDB
9. Frontend dashboard receives real-time updates via WebSocket
```

### Critical Engineering Challenge & Decision

**Challenge:** WhatsApp webhook + LangGraph LLM = 10-30s latency, but webhook needs 200 OK in < 3s.

**Decision:** Use **two-phase processing**:
- Phase 1 (synchronous): Validate, enqueue, return 200
- Phase 2 (async): Full LangGraph workflow via Celery

This means the webhook response does NOT contain the AI reply. The reply is sent asynchronously back through WhatsApp API. This is the correct production pattern.

**Rejected Alternative:** Running LangGraph inline in the webhook would timeout, block resources, and violate WhatsApp's 3-second window. Never do this.

---

## STEP 2: Folder Structure

### 2.1 Backend (`backend/`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app factory, lifespan events
│   ├── config.py                        # Pydantic Settings, env vars, secrets
│   │   Purpose: Centralized configuration with validation
│   │   Responsibilities: Load env vars, validate at startup, expose typed config
│   │   Dependencies: pydantic-settings, python-dotenv
│   │
│   ├── dependencies/
│   │   ├── __init__.py
│   │   ├── auth.py                      # get_current_user, require_role
│   │   │   Purpose: Dependency injection for auth verification
│   │   │   Responsibilities: Decode JWT, verify roles, inject user context
│   │   │   Dependencies: jose, config
│   │   ├── tenant.py                    # get_current_tenant
│   │   │   Purpose: Resolve tenant from request context
│   │   │   Responsibilities: Extract tenant_id from path/token, verify tenant exists
│   │   │   Dependencies: db, cache
│   │   └── database.py                  # get_db, get_redis
│   │       Purpose: Database session management
│   │       Responsibilities: Yield MongoDB client, handle connection pooling
│   │       Dependencies: motor, redis
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── tenant_context.py            # Tenant identification middleware
│   │   │   Purpose: Extract and inject tenant context from webhook
│   │   │   Responsibilities: Parse phone_number_id, lookup tenant, attach to request.state
│   │   │   Dependencies: db, cache
│   │   ├── logging_middleware.py         # Structured request/response logging
│   │   │   Purpose: Structured request/response logging
│   │   │   Responsibilities: Log method, path, duration, status, tenant_id
│   │   │   Dependencies: structlog
│   │   ├── rate_limit.py                # Sliding window rate limiter
│   │   │   Purpose: Per-tenant, per-IP rate limiting
│   │   │   Responsibilities: Check Redis counters, enforce limits, return 429
│   │   │   Dependencies: redis
│   │   └── error_handler.py             # Global exception handler
│   │       Purpose: Catch unhandled exceptions, return structured errors
│   │       Responsibilities: Map exceptions to HTTP status codes, log stack traces
│   │       Dependencies: logging
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py                    # Tenant Pydantic models
│   │   ├── chat.py                      # ChatSession, Message models
│   │   ├── campaign.py                  # BroadcastCampaign models
│   │   ├── user.py                      # Dashboard user models
│   │   ├── webhook.py                   # WhatsApp webhook payload models
│   │   └── langgraph_state.py           # LangGraph state schema
│   │       Purpose: Pydantic models for all domain entities
│   │       Responsibilities: Validation, serialization, OpenAPI generation
│   │       Dependencies: pydantic, datetime
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── whatsapp/
│   │   │   ├── __init__.py
│   │   │   ├── client.py               # HTTP client for WhatsApp Cloud API
│   │   │   │   Purpose: Core HTTP client for WhatsApp API calls
│   │   │   │   Responsibilities: Send text, image, document; handle rate limits (429s), retry
│   │   │   │   Dependencies: httpx, config (access token, phone number ID)
│   │   │   ├── read_receipt.py          # Mark messages as read
│   │   │   ├── typing_indicator.py      # Send typing indicator
│   │   │   ├── text_sender.py           # Send text messages
│   │   │   ├── media_sender.py          # Send image/document messages
│   │   │   └── webhook_verifier.py      # X-Hub-Signature-256 validation
│   │   │       Purpose: Verify webhook authenticity
│   │   │       Responsibilities: HMAC-SHA256 verification of request body
│   │   │       Dependencies: hashlib, hmac
│   │   │
│   │   ├── tenant_service.py           # Tenant CRUD, config management
│   │   ├── chat_service.py             # Conversation management
│   │   ├── message_service.py          # Message persistence, retrieval
│   │   ├── campaign_service.py         # Broadcast campaign logic
│   │   ├── human_handover_service.py   # Escalation management
│   │   └── audit_service.py            # Audit logging
│   │       Purpose: Business logic layer
│   │       Responsibilities: Orchestrate domain operations, enforce business rules
│   │       Dependencies: models, db, cache
│   │
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── whatsapp_graph.py           # LangGraph graph definition
│   │   │   Purpose: Define the LangGraph state machine topology
│   │   │   Responsibilities: Create Graph, add nodes, define edges/routing
│   │   │   Dependencies: langgraph, langchain
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── acknowledge.py          # Mark read + typing indicator
│   │   │   ├── context_retriever.py    # Fetch history + tenant config
│   │   │   ├── sentiment.py            # Sentiment analysis
│   │   │   ├── llm_reasoning.py        # LLM response generation
│   │   │   ├── dispatcher.py           # Route to send or handover
│   │   │   └── human_handover.py       # Notify human agent
│   │   │       Purpose: Individual LangGraph node implementations
│   │   │       Responsibilities: Single responsibility per node, state transformation
│   │   │       Dependencies: services, models
│   │   └── state.py                    # State schema, reducer functions
│   │       Purpose: LangGraph state management
│   │       Responsibilities: Define TypedDict state, custom reducers
│   │       Dependencies: typing, langgraph
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhook.py                  # POST /webhook - WhatsApp inbound
│   │   │   Purpose: Receive WhatsApp webhook events
│   │   │   Responsibilities: Validate signature, enqueue processing, return 200
│   │   │   Dependencies: whatsapp service, celery
│   │   ├── router_v1.py               # API v1 router aggregation
│   │   ├── tenants.py                  # CRUD /api/v1/tenants
│   │   ├── conversations.py            # GET /api/v1/conversations
│   │   ├── messages.py                 # GET /api/v1/messages
│   │   ├── campaigns.py                # CRUD /api/v1/campaigns
│   │   ├── auth.py                     # POST /api/v1/auth/login
│   │   └── monitor.py                  # WS /api/v1/monitor/ws
│   │       Purpose: API route handlers
│   │       Responsibilities: Request parsing, response formatting, auth checks
│   │       Dependencies: services, dependencies
│   │
│   └── core/
│       ├── __init__.py
│       ├── exceptions.py               # Custom exception classes
│       ├── constants.py                # App-wide constants
│       └── types.py                    # Shared type aliases
│
├── workers/
│   ├── __init__.py
│   ├── celery_app.py                   # Celery app instance, broker config
│   │   Purpose: Celery application configuration
│   │   Responsibilities: Create Celery app, configure Redis broker, auto-discover tasks
│   │   Dependencies: celery, redis
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── process_message.py          # Main webhook processing task
│   │   └── broadcast_campaign.py       # Scheduled campaign execution
│   │       Purpose: Async task definitions
│   │       Responsibilities: Execute LangGraph workflow, handle retries
│   │       Dependencies: workflows, services
│   └── scheduler.py                    # Celery Beat schedule
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Fixtures: MongoDB mock, test tenant, test client
│   ├── test_webhook.py
│   ├── test_whatsapp_service.py
│   ├── test_langgraph.py               # Test full graph + individual nodes
│   ├── test_services/
│   ├── test_api/
│   └── fixtures/
│       ├── webhook_payloads.json        # Sample webhook payloads for testing
│       └── mock_whatsapp_server.py      # Mock WhatsApp API for integration tests
│
├── migrations/
│   ├── 001_create_tenants.py
│   ├── 002_create_chat_sessions.py
│   └── 003_create_indexes.py
│       Purpose: Index and schema migrations
│       Responsibilities: Create MongoDB indexes, update schemas
│       Dependencies: motor
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
└── .flake8
```

### 2.2 Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── app/                            # Next.js App Router pages
│   │   ├── layout.tsx                  # Root layout, providers
│   │   ├── page.tsx                    # Redirect to /login
│   │   ├── login/
│   │   │   └── page.tsx                # Login with Auth0 / JWT
│   │   ├── dashboard/
│   │   │   ├── layout.tsx              # Dashboard layout with sidebar
│   │   │   ├── page.tsx                # Overview / metrics
│   │   │   ├── conversations/
│   │   │   │   └── page.tsx            # Live conversation list
│   │   │   ├── conversation/
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx        # Single conversation viewer
│   │   │   ├── campaigns/
│   │   │   │   └── page.tsx            # Broadcast campaign manager
│   │   │   ├── escalation/
│   │   │   │   └── page.tsx            # Human escalation queue
│   │   │   └── settings/
│   │   │       └── page.tsx            # Tenant settings
│   │   └── switch-tenant/
│   │       └── page.tsx                # Tenant switcher
│   │
│   ├── components/
│   │   ├── ui/                         # Atomic UI components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Table.tsx
│   │   │   ├── Spinner.tsx
│   │   │   └── Toast.tsx
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx            # Navigation sidebar
│   │   │   ├── Header.tsx             # Top header with tenant selector
│   │   │   └── TenantSwitcher.tsx     # Dropdown to switch tenants
│   │   ├── chat/
│   │   │   ├── MessageBubble.tsx       # Individual message display
│   │   │   ├── MessageList.tsx         # Scrollable message list
│   │   │   ├── ChatInput.tsx           # Human agent reply input
│   │   │   ├── TypingIndicator.tsx     # AI typing animation
│   │   │   └── MediaPreview.tsx        # Image/document preview
│   │   ├── conversations/
│   │   │   ├── ConversationList.tsx    # Filterable conversation sidebar
│   │   │   ├── ConversationCard.tsx    # Summary card per conversation
│   │   │   └── StatusBadge.tsx         # Active/escalated/resolved badge
│   │   ├── campaigns/
│   │   │   ├── CampaignList.tsx
│   │   │   ├── CampaignForm.tsx
│   │   │   └── CampaignAnalytics.tsx
│   │   └── escalation/
│   │       ├── EscalationQueue.tsx     # Queue list
│   │       └── EscalationCard.tsx      # Individual escalation item
│   │
│   ├── hooks/
│   │   ├── useAuth.ts                 # Auth state, login/logout
│   │   ├── useWebSocket.ts            # WebSocket connection management
│   │   ├── useConversations.ts        # Conversation data fetching
│   │   ├── useMessages.ts             # Message fetching + real-time updates
│   │   └── useTenant.ts               # Current tenant state
│   │
│   ├── lib/
│   │   ├── api.ts                     # Axios/fetch wrapper with auth
│   │   ├── websocket.ts               # WebSocket client singleton
│   │   └── utils.ts                   # Date formatting, phone formatting
│   │
│   ├── providers/
│   │   ├── AuthProvider.tsx            # Auth context provider
│   │   └── TenantProvider.tsx          # Tenant context provider
│   │
│   ├── store/
│   │   ├── authStore.ts               # Zustand auth store
│   │   ├── conversationStore.ts        # Zustand conversation store
│   │   └── tenantStore.ts             # Zustand tenant store
│   │
│   └── styles/
│       ├── globals.css
│       └── tailwind.css
│
├── public/
│   └── assets/
│       ├── logo.svg
│       └── illustrations/
│
├── tests/
│   ├── components/
│   └── hooks/
│
├── Dockerfile
├── next.config.js
├── package.json
├── tsconfig.json
├── tailwind.config.js
├── .env.local.example
└── .eslintrc.json
```

### 2.3 Docs (`docs/`)

```
docs/
├── README.md                           # Project overview
├── ARCHITECTURE.md                     # This document
├── api/
│   ├── webhook.md                      # Webhook contract spec
│   ├── rest-api.md                     # All REST endpoints
│   └── websocket.md                    # WebSocket event types
├── deployment/
│   ├── environment-variables.md        # All env vars per service
│   ├── docker-compose.md               # Local dev setup
│   └── production-deployment.md        # Cloud Run / Render setup
├── runbooks/
│   ├── onboarding-tenant.md            # Steps to add new tenant
│   ├── debugging-webhooks.md           # Webhook troubleshooting
│   └── incident-response.md            # Downtime / error procedures
└── decisions/
    ├── 001-use-celery-over-backgroundtasks.md
    ├── 002-mongodb-over-postgres.md
    └── 003-langgraph-over-dialogflow.md
        Purpose: Architecture Decision Records (ADRs)
        Responsibilities: Document rationale for key decisions
        Dependencies: N/A
```

---

## STEP 3: MongoDB Collections

### Design Principles

1. **Multi-tenant via `tenant_id` field on every document** — not separate databases. This allows:
   - Efficient resource utilization
   - Cross-tenant analytics (opt-in)
   - Simpler backup/restore
   - **BUT** requires careful index design to prevent "noisy neighbor" queries

2. **Shard key = `tenant_id`** for horizontal scaling (MongoDB Atlas)

3. **All timestamps in UTC, stored as BSON Date**

4. **Use `$natural` sort only on capped collections** — otherwise always index

### 3.1 `tenants`

**Purpose:** Store tenant (company) configuration, WhatsApp credentials, AI settings.

**Schema:**

```json
{
  "_id": ObjectId("660abc..."),
  "tenant_id": UUID("550e8400-e29b-41d4-a716-446655440000"),
  "name": "Furniture Store Inc.",
  "slug": "furniture-store",
  "status": "active",                    // active | paused | suspended | deleted

  "whatsapp": {
    "phone_number_id": "123456789",
    "business_account_id": "987654321",
    "access_token": "EAAT...encrypted...",
    "webhook_secret": "whsec_...encrypted...",
    "api_version": "v21.0"
  },

  "ai_config": {
    "system_prompt": "You are a helpful sales assistant for a furniture store...",
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_tokens": 1024,
    "sentiment_threshold": 0.7,
    "confidence_threshold": 0.8,
    "human_handover_threshold": 0.6,
    "language": "en",
    "allowed_media_types": ["image", "document"],
    "keywords_triggers": ["speak to manager", "complaint", "refund"]
  },

  "settings": {
    "timezone": "America/New_York",
    "business_hours": {
      "monday": {"start": "09:00", "end": "18:00"},
      "tuesday": {"start": "09:00", "end": "18:00"},
      "sunday": {"closed": true}
    },
    "typing_indicator_enabled": true,
    "read_receipts_enabled": true,
    "auto_reply_enabled": true,
    "business_name": "Furniture Store"
  },

  "media_library": [
    {
      "media_id": "media_uuid_1",
      "type": "image",
      "url": "https://storage.googleapis.com/...",
      "caption": "Summer Collection 2026",
      "tags": ["summer", "sofa", "promo"],
      "active": true,
      "created_at": ISODate("2026-01-01T00:00:00Z")
    }
  ],

  "billing_plan": "professional",        // starter | professional | enterprise
  "max_concurrent_conversations": 1000,
  "messages_this_month": 45231,
  "messages_limit": 100000,

  "metadata": {
    "created_by": "admin@opencode.ai",
    "onboarded_at": ISODate("2026-01-01T00:00:00Z")
  },

  "created_at": ISODate("2026-01-01T00:00:00Z"),
  "updated_at": ISODate("2026-06-20T00:00:00Z")
}
```

**Indexes:**

```javascript
// Primary lookup by phone_number_id (webhook needs this in < 5ms)
{ "whatsapp.phone_number_id": 1 }

// Unique tenant slug for dashboard
{ "slug": 1 }, { unique: true }

// Tenant ID unique
{ "tenant_id": 1 }, { unique: true }

// Status filter for admin listing
{ "status": 1, "created_at": -1 }

// Partial index for active tenants only
{ "status": 1, "whatsapp.phone_number_id": 1 }, { partialFilterExpression: { status: "active" } }
```

### 3.2 `chat_sessions`

**Purpose:** Represents a conversation between a customer and the AI/human agent within a tenant.

**Schema:**

```json
{
  "_id": ObjectId("660abc..."),
  "session_id": UUID("660e8400-e29b-41d4-a716-446655440001"),
  "tenant_id": UUID("550e8400-e29b-41d4-a716-446655440000"),

  "customer": {
    "wa_id": "1234567890",               // WhatsApp ID (phone number)
    "profile_name": "John Doe",
    "language": "en"
  },

  "status": "active",                    // active | waiting | human_handover | resolved | closed
  "mode": "ai",                          // ai | human | mixed

  "channel": "whatsapp",                 // For future: instagram, web

  "message_count": 24,
  "last_message_at": ISODate("2026-06-20T12:30:00Z"),
  "last_message_preview": "When will my order arrive?",

  "sentiment_summary": {
    "overall": "neutral",                // positive | neutral | negative
    "average_score": 0.12,
    "last_score": -0.45,
    "updated_at": ISODate("2026-06-20T12:30:00Z")
  },

  "escalation": {
    "is_escalated": false,
    "escalated_at": null,
    "escalated_by": null,                // "ai" | "customer" | "agent_phone"
    "resolved_at": null,
    "assigned_to": null,
    "reason": null
  },

  "tags": ["order-inquiry", "return"],
  "priority": "normal",                  // low | normal | high | urgent

  "created_at": ISODate("2026-06-20T10:00:00Z"),
  "updated_at": ISODate("2026-06-20T12:30:00Z")
}
```

**Indexes:**

```javascript
// Primary query: get active sessions for a tenant
{ "tenant_id": 1, "status": 1, "last_message_at": -1 }

// Find session by customer WA ID in a tenant
{ "tenant_id": 1, "customer.wa_id": 1, "status": 1 }

// Escalation queue query
{ "tenant_id": 1, "escalation.is_escalated": 1, "priority": 1, "last_message_at": -1 }

// Active session lookup for incoming message dedup
{ "tenant_id": 1, "customer.wa_id": 1, "status": { $ne: "closed" } }

// TTL index - auto-archive closed sessions after 90 days
{ "status": 1, "updated_at": 1 }, { partialFilterExpression: { status: "closed" }, expireAfterSeconds: 7776000 }
```

### 3.3 `messages`

**Purpose:** Individual messages within a chat session. Supports text, image, document types.

**Schema:**

```json
{
  "_id": ObjectId("660abc..."),
  "message_id": UUID("770e8400-e29b-41d4-a716-446655440002"),
  "tenant_id": UUID("550e8400-e29b-41d4-a716-446655440000"),
  "session_id": UUID("660e8400-e29b-41d4-a716-446655440001"),

  "role": "customer",                    // customer | ai | human | system
  "type": "text",                        // text | image | document | interactive | system

  "content": {
    "text": "When will my order arrive?",
    // For image:
    "media_id": "media_uuid_123",
    "media_url": "https://storage.googleapis.com/...",
    "mime_type": "image/jpeg",
    "caption": "Photo of damaged item",
    "file_size": 2048576
  },

  "whatsapp": {
    "wam_id": "wamid_abc123",            // WhatsApp Message ID (for receipts)
    "message_type": "text",
    "from": "1234567890",
    "to_phone_number_id": "123456789",
    "status": "sent"                     // sent | delivered | read | failed
  },

  "ai_metadata": {
    "confidence": 0.92,
    "sentiment_score": 0.12,
    "sentiment_label": "neutral",
    "processing_time_ms": 2340,
    "model_used": "gpt-4o",
    "tokens_used": 456,
    "was_escalated": false
  },

  "is_escalation_point": false,
  "tags": [],

  "created_at": ISODate("2026-06-20T12:29:45Z")
}
```

**Indexes:**

```javascript
// Primary: get messages for a session (paginated)
{ "session_id": 1, "created_at": 1 }

// Tenant-scoped queries
{ "tenant_id": 1, "session_id": 1, "created_at": -1 }

// WhatsApp dedup (prevent double processing)
{ "whatsapp.wam_id": 1 }, { unique: true, sparse: true }

// Media queries for tenant media library
{ "tenant_id": 1, "type": "image", "created_at": -1 }

// Audit: messages containing escalation
{ "tenant_id": 1, "is_escalation_point": 1, "created_at": -1 }

// Compound for conversation list
{ "session_id": 1, "created_at": -1 }
```

### 3.4 `broadcast_campaigns`

**Purpose:** Scheduled bulk messaging campaigns to multiple customers.

**Schema:**

```json
{
  "_id": ObjectId("660abc..."),
  "campaign_id": UUID("880e8400-e29b-41d4-a716-446655440003"),
  "tenant_id": UUID("550e8400-e29b-41d4-a716-446655440000"),

  "name": "Summer Sale 2026",
  "status": "draft",                     // draft | scheduled | running | paused | completed | cancelled

  "message_template": {
    "type": "text",                      // text | image | document | template
    "content": {
      "text": "Check out our summer sale! 50% off all sofas.",
      "media_id": "media_uuid_1",
      "media_url": "https://...",
      "caption": "Summer Sale Banner"
    },
    "language": "en"
  },

  "target_audience": {
    "filter_criteria": {
      "tags": ["returning-customer"],
      "min_confidence": null,
      "last_interaction_before": null,
      "last_interaction_after": ISODate("2026-05-01T00:00:00Z")
    },
    "customer_wa_ids": [],               // Explicit list or null
    "estimated_reach": 5000
  },

  "schedule": {
    "type": "scheduled",                 // now | scheduled | recurring
    "send_at": ISODate("2026-07-01T10:00:00Z"),
    "timezone": "America/New_York",
    "recurrence": null                   // null | daily | weekly | monthly
  },

  "delivery_stats": {
    "total": 5000,
    "sent": 2341,
    "delivered": 2200,
    "read": 1500,
    "failed": 41,
    "replied": 89,
    "opt_outs": 5
  },

  "created_by": "user_uuid_1",
  "approved_by": "user_uuid_2",

  "created_at": ISODate("2026-06-15T00:00:00Z"),
  "updated_at": ISODate("2026-06-20T00:00:00Z")
}
```

**Indexes:**

```javascript
// Tenant campaigns list
{ "tenant_id": 1, "status": 1, "created_at": -1 }

// Scheduler: find campaigns due for execution
{ "status": "scheduled", "schedule.send_at": 1 }

// Status-based queries for dashboard
{ "tenant_id": 1, "status": 1 }
```

### 3.5 `audit_logs`

**Purpose:** Immutable log of all significant system events. Append-only.

**Schema:**

```json
{
  "_id": ObjectId("660abc..."),
  "audit_id": UUID("990e8400-e29b-41d4-a716-446655440004"),
  "tenant_id": UUID("550e8400-e29b-41d4-a716-446655440000"),

  "event_type": "message.sent",          // tenant.created | message.sent | escalation.triggered | campaign.started | human.assigned | settings.updated
  "severity": "info",                    // info | warn | error | critical

  "actor": {
    "type": "system",                    // system | ai | human | customer
    "id": null,                          // user_id, wa_id, or system
    "email": null
  },

  "resource": {
    "type": "message",                   // tenant | session | message | campaign | settings
    "id": "770e8400-..."
  },

  "details": {
    "summary": "AI sent text message to customer",
    "changes": null,                     // { field: "old_value", "new_value" } for config changes
    "request_id": "req_abc123",
    "ip_address": null
  },

  "created_at": ISODate("2026-06-20T12:30:00Z")
}
```

**Indexes:**

```javascript
// Primary: tenant-scoped time-series queries
{ "tenant_id": 1, "created_at": -1 }

// Event-type filtering for dashboards
{ "tenant_id": 1, "event_type": 1, "created_at": -1 }

// Severity-based alerting
{ "severity": 1, "created_at": -1 }, { partialFilterExpression: { severity: { $in: ["error", "critical"] } } }

// Resource lookup
{ "resource.type": 1, "resource.id": 1, "created_at": -1 }

// TTL: auto-delete audit logs after 1 year (regulatory compliance)
{ "created_at": 1 }, { expireAfterSeconds: 31536000 }
```

### Multi-Tenant Isolation Strategy

| Concern | Strategy |
|---------|----------|
| **Data Isolation** | All collections have `tenant_id` index. Every query MUST include `tenant_id` filter. Repository layer enforces this. |
| **Performance Isolation** | Shard key = `tenant_id` (hashed) across Atlas cluster. A noisy tenant's queries cannot degrade others. |
| **Rate Limits** | Per-tenant rate limiting in middleware (Redis sliding window). |
| **Storage Isolation** | Atlas cluster with priority rules — enterprise tenants get IOPS priority. |
| **Query Injection** | Parameterized queries only. Never concatenate user input into queries. |
| **Backup Isolation** | Tenant-level backups using `mongodump --query` with `tenant_id` filter. |
| **Deletion** | Soft-delete via `status: "deleted"`. Hard-delete after 30-day grace period. |

**Critical Warning:** Never write a query without `tenant_id` filter in a multi-tenant system. One missing filter = data leak across all tenants. Enforce this at the repository/DAO layer using a base class that automatically appends `tenant_id`.

---

## STEP 4: LangGraph Architecture

### 4.1 State Schema

```python
# backend/app/workflows/state.py

class GraphState(TypedDict):
    # Immutable (set once at start)
    tenant_id: str
    session_id: str
    customer_wa_id: str
    incoming_message: MessageModel
    phone_number_id: str

    # Accumulated state
    conversation_history: Annotated[list, add_messages]  # LangChain message list
    tenant_config: Optional[TenantModel]

    # Analysis results
    sentiment: Optional[SentimentResult]
    confidence: Optional[float]
    needs_human_handover: bool

    # Output
    response_type: Optional[str]          # text | image | document | handover
    response_content: Optional[dict]

    # Metadata
    errors: Annotated[list[str], add]    # Accumulated error messages
    retry_count: int
    processing_started_at: datetime
```

### 4.2 Graph Topology

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#1a1a2e', 'primaryTextColor': '#e0e0e0', 'primaryBorderColor': '#4a4a6a', 'lineColor': '#6a6a8a'}}}%%

stateDiagram-v2
    [*] --> Acknowledge: Webhook received
    Acknowledge --> ContextRetriever: Mark read + typing sent
    
    ContextRetriever --> SentimentAnalysis: History + config loaded
    
    SentimentAnalysis --> LLMReasoning: Sentiment scored
    
    LLMReasoning --> Dispatcher: Response generated
    
    state Dispatcher <<choice>>
    
    Dispatcher --> SendText: confidence >= 0.8 & type=text
    Dispatcher --> SendImage: confidence >= 0.8 & type=image
    Dispatcher --> SendDocument: confidence >= 0.8 & type=document
    
    Dispatcher --> HumanHandover: confidence < 0.6
    Dispatcher --> HumanHandover: sentiment < threshold
    
    HumanHandover --> Dispatcher: Agent resolves
    
    SendText --> [*]
    SendImage --> [*]
    SendDocument --> [*]
    HumanHandover --> [*]: Agent marks complete
```

### 4.3 Node Definitions

#### Node 1: Acknowledge Node

```
Purpose:     Immediately mark message as read + send typing indicator
Input:       incoming_message, tenant_config
Output:      Same state + acknowledgment_sent flag
Timeout:     10 seconds
Retry:       1 retry, 500ms apart (WhatsApp API may be slow)
Failure:     Log warning, proceed to ContextRetriever anyway
               (read receipts are non-critical — don't block the flow)
```

**Implementation notes:**
- Fire WhatsApp API calls concurrently (asyncio.gather)
- If WhatsApp API returns 429, backoff and skip (don't block graph)
- This node must never fail the entire workflow

#### Node 2: Context Retriever

```
Purpose:     Load conversation history + tenant configuration
Input:       session_id, tenant_id
Output:      conversation_history, tenant_config
Timeout:     15 seconds
Retry:       2 retries with exponential backoff (1s, 3s)
Failure:     ❌ CRITICAL — cannot proceed without tenant config
               If MongoDB is down, fail the entire graph → DLQ
```

**Data loaded:**
1. Chat session document
2. Last N messages (configurable, default 50)
3. Tenant AI config (system prompt, thresholds)
4. Customer context (past sessions summary)
5. Media library (for dispatcher to select images)

**Optimization:** Cache tenant config in Redis with 60s TTL. Cache conversation summary in Redis.

#### Node 3: Sentiment Analysis Node

```
Purpose:     Analyze incoming message + recent history for sentiment
Input:       incoming_message, recent_history (last 5 messages)
Output:      sentiment (positive/neutral/negative) + score (-1 to 1)
Timeout:     5 seconds
Retry:       1 retry
Failure:     Default to neutral (0.0), continue workflow
               Sentiment is advisory, not critical
```

**Approach:** Use a fast, lightweight model:
- **Option A (Recommended):** LLM-as-judge — single prompt to GPT-4o-mini: "Classify sentiment of this message. Return JSON {score, label, reasoning}"
- **Option B:** Fine-tuned classifier (distilbert) — faster but requires MLOps pipeline
- **Option C:** VADER + keyword rules (fastest, zero-cost, good enough for MVP)

**Decision: Use Option A for MVP, migrate to Option C + B as volume grows.**

**Why not dedicated model for MVP?** Sentiment is not core to WhatsApp flow. We need 95% accuracy, not 99%. Adding a separate model deployment adds DevOps complexity with minimal benefit at this stage.

#### Node 4: LLM Reasoning Node

```
Purpose:     Generate response using tenant-specific AI prompt
Input:       conversation_history, tenant_config, sentiment, incoming_message
Output:      response_type, response_content, confidence
Timeout:     30 seconds (LLM API call)
Retry:       2 retries with exponential backoff (2s, 5s)
Failure:     ❌ CRITICAL — cannot proceed without response
               If all retries exhausted, route to human handover
```

**Prompt template:**

```
System: {tenant_config.system_prompt}
Sentiment of customer: {sentiment.label} (score: {sentiment.score})
Conversation history:
{formatted_history}

Available media (use only if directly relevant):
{media_library}

Rules:
1. Keep responses under 1024 characters (WhatsApp limit)
2. If customer is upset, apologize first, then help
3. If customer asks for human, extract to handover
4. Response MUST be JSON: {type, text, media_id (optional), confidence, reason}

Customer: {incoming_message}
AI:
```

**Key design decisions:**
- Structured output (JSON mode) — parse response deterministically
- Confidence score 0.0-1.0 from LLM's self-assessment
- If confidence < tenant threshold → handover
- If response_type = "image" → dispatcher selects best image from media library

#### Node 5: Dispatcher Node

```
Purpose:     Execute the chosen response (send message via WhatsApp API)
Input:       response_type, response_content, confidence, sentiment
Output:      message_sent confirmation
Timeout:     15 seconds per API call
Retry:       3 retries with exponential backoff (1s, 3s, 7s)
Failure:     If send fails after all retries → audit error, notify ops
```

**Decision logic:**

```
if needs_human_handover or confidence < tenant.human_handover_threshold:
    → route to HumanHandover node
    
if confidence >= tenant.confidence_threshold:
    if response_type == "text":
        → send_text_message()
    elif response_type == "image":
        → select_best_media() → send_image_message()
    elif response_type == "document":
        → select_best_media() → send_document_message()
    → persist message to MongoDB
    → return SUCCESS
    
# Edge case: high confidence with low sentiment
if confidence >= 0.8 and sentiment.score < -0.7:
    → send text + notify human agent (watching mode)
```

#### Node 6: Human Handover Node

```
Purpose:     Transfer conversation to human agent
Input:       session_id, reason, context_summary
Output:      Escalation created, agent notified
Timeout:     10 seconds
Retry:       2 retries
Failure:     Log critical error, message remains in queue
```

**Actions:**
1. Update session: `status = "human_handover"`, `mode = "mixed"`
2. Create escalation record
3. Push WebSocket event to dashboard (`escalation.new`)
4. Optional: Send SMS/pager notification to on-call agent
5. Send auto-reply to customer: "One moment please, I'm connecting you with a human agent."
6. Once agent resolves → update session, transition graph back to Dispatcher

### 4.4 Failure Handling & Retry Strategy

| Node | Retries | Backoff | Failure Mode |
|------|---------|---------|--------------|
| Acknowledge | 1 | 500ms | Log warning, continue |
| Context Retriever | 2 | 1s, 3s | ❌ DLQ if MongoDB down |
| Sentiment Analysis | 1 | 500ms | Default neutral, continue |
| LLM Reasoning | 2 | 2s, 5s | ❌ Route to human handover |
| Dispatcher | 3 | 1s, 3s, 7s | ❌ Dead Letter Queue |
| Human Handover | 2 | 1s, 3s | ❌ Log critical, alert |

**Dead Letter Queue (DLQ):** After all retries exhausted, message goes to `failed_messages` collection. Ops team reviews daily. DLQ messages can be manually re-queued via dashboard.

**Graph-level timeout:** 120 seconds max. If graph exceeds this, Celery task fails and goes to DLQ.

### 4.5 LangGraph vs. Alternative Decisions

**Challenged Decision: "Why LangGraph and not a simple if-else chain?"**

**Answer:** LangGraph provides:
1. **State management** — automatic history accumulation via reducers
2. **Conditional routing** — dynamic dispatch based on confidence/sentiment
3. **Observability** — built-in tracing via LangSmith
4. **Human-in-the-loop** — native `interrupt`/`resume` for handover
5. **Checkpointing** — graph can pause and resume (future-proofing)

For MVP, you *could* use a simple chain. But swapping from chain to graph after 10k conversations is a painful migration. Start with LangGraph.

**Challenged Decision: "Why not Dialogflow / Rasa / Voiceflow?"**

**Verdict:** Those are low-code platforms that sacrifice control. LangGraph gives us:
- Full control over prompt engineering
- Custom state transitions
- No vendor lock-in
- Ability to run anywhere (not just Google Cloud)

---

## STEP 5: WhatsApp Integration Layer

### 5.1 Service Layer Architecture

```
┌─────────────────────────────────────────┐
│           WhatsApp Service               │
│  (Single public interface for API)       │
├─────────────────────────────────────────┤
│  + send_text(to, text, preview_url?)     │
│  + send_image(to, media_id, caption?)    │
│  + send_document(to, media_id, caption?) │
│  + mark_read(message_id)                 │
│  + send_typing(to, action)               │
│  + upload_media(file) → media_id         │
└─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│         WhatsApp Client (httpx)          │
│  (Internal HTTP client wrapper)          │
├─────────────────────────────────────────┤
│  - Base URL: graph.facebook.com/v21.0   │
│  - Auto-injects access token             │
│  - Rate limit detection (429)            │
│  - Retry with exponential backoff        │
│  - Structured error handling             │
└─────────────────────────────────────────┘
```

### 5.2 Read Receipts

```python
# POST /{phone-number-id}/messages
{
    "messaging_product": "whatsapp",
    "status": "read",
    "message_id": "wamid_abc123"   # From incoming webhook
}
```

**Design decisions:**
- Called from Acknowledge node, immediately after webhook received
- Non-blocking — fire-and-forget with 1 retry
- MUST use the original `wamid` from webhook payload
- Rate limit: 10 reads per second per phone number (WhatsApp limit)

### 5.3 Typing Indicator

```python
# POST /{phone-number-id}/messages
# Start typing:
{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "1234567890",
    "type": "action",
    "action": "typing_on"
}

# Stop typing:
{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "1234567890",
    "type": "action",
    "action": "typing_off"
}
```

**Design decisions:**
- Send `typing_on` at start of Acknowledge node
- Send `typing_off` just before Dispatcher sends response
- WhatsApp auto-expires typing indicator after ~20s, so we need to refresh if LLM takes > 15s
- Refresh via a heartbeat: re-send `typing_on` every 10s while processing

### 5.4 Text Messages

```python
# POST /{phone-number-id}/messages
{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "1234567890",
    "type": "text",
    "text": {
        "preview_url": false,
        "body": "Your order has shipped! Tracking: 1Z999AA10123456784"
    }
}
```

**Constraints:**
- Max 4096 characters (but we limit to 1024 for readability)
- `preview_url: true` if message contains URLs (auto-generates link preview)
- Must handle WhatsApp message template requirements for proactive messages

### 5.5 Image Messages

```python
# POST /{phone-number-id}/messages
{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "1234567890",
    "type": "image",
    "image": {
        "id": "media_uuid_123",          # Previously uploaded media ID
        "caption": "Here's our Summer Collection sofa!"
    }
}
```

**Prerequisites:**
1. Media must be uploaded to WhatsApp servers first via `POST /{phone-number-id}/media`
2. Media ID expires after 30 days — re-upload if needed
3. Supported formats: JPEG, PNG, WEBP (max 5MB, 1024x1024 recommended)

### 5.6 Document Messages

```python
# POST /{phone-number-id}/messages
{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "1234567890",
    "type": "document",
    "document": {
        "id": "media_uuid_456",
        "caption": "Product Catalog 2026",
        "filename": "catalog-2026.pdf"
    }
}
```

**Constraints:**
- Supported: PDF, DOCX, PPTX, XLSX (max 100MB)
- `filename` field is REQUIRED for documents
- Media must be uploaded first (same as images)

### 5.7 Webhook Handler

```python
# POST /webhook
# Meta sends:
{
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "987654321",
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                    "phone_number_id": "123456789",
                    "display_phone_number": "15551234567"
                },
                "contacts": [{
                    "profile": {"name": "John Doe"},
                    "wa_id": "1234567890"
                }],
                "messages": [{
                    "from": "1234567890",
                    "id": "wamid_abc123",
                    "timestamp": "1718888888",
                    "type": "text",
                    "text": {"body": "When will my order arrive?"}
                }]
            },
            "field": "messages"
        }]
    }]
}
```

**Parsing logic:**
1. Extract `phone_number_id` from metadata
2. Lookup tenant in MongoDB (cached in Redis)
3. Extract message type and content
4. Create `IncomingMessage` Pydantic model
5. Enqueue processing task

### 5.8 Service Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                   WHATSAPP SERVICE LAYER                    │
├─────────────┬───────────────┬────────────────┬──────────────┤
│  Messages   │   Actions     │   Media        │  Templates   │
│  Service    │   Service     │   Service      │  Service     │
├─────────────┼───────────────┼────────────────┼──────────────┤
│ send_text() │ mark_read()   │ upload_media() │ create_tmpl()│
│ send_image()│ typing_on()   │ get_media_url()│ send_tmpl()  │
│ send_doc()  │ typing_off()  │ delete_media() │              │
└─────────────┴───────────────┴────────────────┴──────────────┘
         │            │               │               │
         └────────────┴───────┬───────┴───────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  HttpClient       │
                    │  (httpx, retry)   │
                    │  Base: graph...   │
                    └───────────────────┘
```

**Why separate services?**
- Single Responsibility: Each handles one API domain
- Testability: Mock individual services
- Future: Instagram layer can share client but needs different endpoint logic

---

## STEP 6: Async Processing Architecture

### 6.1 The Core Problem

WhatsApp requires a `200 OK` response within 3 seconds. LangGraph with LLM takes 10-30 seconds. This is an **inherent architectural mismatch**.

**Solution:** Two-phase processing.

```
Phase 1 (Synchronous, < 3s):
  1. Receive webhook
  2. Validate signature
  3. Parse payload
  4. Lookup tenant
  5. Enqueue to Celery
  6. Return 200 OK

Phase 2 (Asynchronous, 10-30s):
  1. Celery worker picks up task
  2. Run LangGraph workflow
  3. Send response back through WhatsApp API
```

### 6.2 Current Architecture (MVP): FastAPI BackgroundTasks

```python
# backend/app/api/webhook.py
from fastapi import BackgroundTasks

@router.post("/webhook")
async def receive_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant_from_webhook)
):
    # 1. Validate signature
    verify_signature(request)

    # 2. Enqueue processing
    background_tasks.add_task(
        process_message_task,
        tenant_id=str(tenant.tenant_id),
        message=payload.extract_message()
    )

    # 3. Return immediately
    return {"status": "ok"}
```

**Why this works for MVP:**
- Zero infrastructure: no Redis, no Celery needed
- FastAPI uses `asyncio.create_task` internally — lightweight
- Single process, no serialization overhead
- Perfect for initial deployment (1-2 workers)

**⚠️ Critical limitations:**
- Task lost if worker crashes (no persistence)
- No retry mechanism (task dies on exception)
- No monitoring (can't see queue depth)
- No prioritization
- No concurrency control (all tasks compete for same worker)

**When to migrate from BackgroundTasks to Celery:**
- When you have > 3 tenants
- When you need > 2 webhook workers
- When a single failed task causes user-visible issues
- When you need to schedule broadcast campaigns

### 6.3 Future Architecture: Celery + Redis

```mermaid
%%{init: {'theme': 'dark'}}%%

graph LR
    WH[Webhook Receiver] -->|enqueue| RQ[Redis Queue]
    RQ -->|dequeue| W1[Celery Worker 1]
    RQ -->|dequeue| W2[Celery Worker 2]
    RQ -->|dequeue| WN[Celery Worker N]
    W1 --> LG[LangGraph]
    W2 --> LG
    WN --> LG
    LG --> WA[WhatsApp API]
    
    SCH[Celery Beat] -->|schedule| RQ
    
    RQ --> MON[Redis Monitor<br/>Queue Depth]
    MON --> DASH[Dashboard]
```

**Celery Configuration:**

```python
# backend/workers/celery_app.py
from celery import Celery

celery_app = Celery(
    "whatsapp_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=180,           # 3 minutes max per task
    task_soft_time_limit=150,      # Soft limit, triggers SoftTimeLimitExceeded
    task_acks_late=True,           # Re-deliver if worker crashes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_routes={
        "process_message": {"queue": "messages"},
        "run_campaign": {"queue": "campaigns"},
    },
    task_default_rate_limit="50/m",  # Per-worker rate limit
)
```

### 6.4 Scaling Strategy

| Component | Scaling Approach | Trigger |
|-----------|-----------------|---------|
| Webhook API (FastAPI) | Horizontal: behind Cloud Run LB | CPU > 70% or queue depth > 100 |
| Celery Workers | Horizontal: add workers | Queue depth consistently > 1000 |
| MongoDB | Vertical: Atlas tier upgrade | P95 query latency > 100ms |
| Redis | Vertical: larger instance | Memory usage > 70% |
| LLM API | Horizontal: queue depth + retry | Rate limit errors (429) |

**Auto-scaling rule for Celery:**

```
Queue depth < 100:  min workers = 2
Queue depth 100-1000: scale up 1 worker per 100 messages
Queue depth > 1000:  max workers = 20
```

**Note:** Celery auto-scaling (`--autoscale`) is NOT recommended. It's unreliable. Use Kubernetes HPA or a custom scaling script based on Redis queue length.

### 6.5 Task Prioritization

Use separate queues:
- `messages` — high priority, processed immediately
- `campaigns` — low priority, batch-processed with rate limiting
- `dlq` — failed messages for manual review

```python
@router.post("/webhook")
async def receive_webhook(...):
    process_message_task.apply_async(
        args=[payload],
        queue="messages",
        priority=10,              # Higher = more urgent
        expires=300               # Task expires after 5 minutes
    )
```

---

## STEP 7: Frontend Dashboard

### 7.1 Tech Stack Decision

| Concern | Recommendation | Rationale |
|---------|---------------|-----------|
| Framework | Next.js 14+ (App Router) | SSR for dashboard, API routes if needed |
| State | Zustand | Lightweight, TypeScript-native, no boilerplate |
| Styling | Tailwind CSS + shadcn/ui | Production-ready, accessible, fast |
| Real-time | WebSocket (FastAPI) | Bidirectional, low-latency |
| Auth | Auth0 or next-auth | Social login, MFA, JWT management |
| Charts | Recharts | Simple, composable, React-native |
| Build | Vercel | Optimized for Next.js, edge functions |

### 7.2 Page Hierarchy

```mermaid
%%{init: {'theme': 'dark'}}%%

graph TB
    ROOT[App Root] --> LOGIN[Login Page]
    ROOT --> DASH[Dashboard Layout]
    
    DASH --> OVER[Overview<br/>/dashboard]
    DASH --> CONV[Conversations<br/>/dashboard/conversations]
    DASH --> CHAT[Chat Viewer<br/>/dashboard/conversation/:id]
    DASH --> CAMP[Campaigns<br/>/dashboard/campaigns]
    DASH --> ESC[Escalations<br/>/dashboard/escalation]
    DASH --> SETT[Settings<br/>/dashboard/settings]
    DASH --> SWTCH[Switch Tenant<br/>/switch-tenant]
    
    CHAT --> MSG[Message List]
    CHAT --> INPUT[Chat Input<br/>Human Reply]
    CHAT --> MEDIA[Media Preview]
    CHAT --> INFO[Customer Info Panel]
    
    OVER --> STATS[Stats Cards]
    OVER --> CHRT[Sentiment Chart]
    OVER --> ACTV[Active Conversations]
    
    CONV --> LIST[Conversation List]
    CONV --> FLTR[Filter Bar<br/>Status / Date / Sentiment]
    
    ESC --> Q[Escalation Queue]
    ESC --> DTL[Escalation Detail]
    
    CAMP --> CLIST[Campaign List]
    CAMP --> CFORM[Campaign Form]
    CAMP --> CANL[Campaign Analytics]
```

### 7.3 Component Hierarchy

```
<App>
  <AuthProvider>
    <TenantProvider>
      <Layout>
        <Sidebar>
          <TenantSwitcher />
          <NavItem icon="dashboard" href="/dashboard" />
          <NavItem icon="chat" href="/dashboard/conversations" />
          <NavItem icon="campaign" href="/dashboard/campaigns" />
          <NavItem icon="alert" href="/dashboard/escalation" />
          <NavItem icon="settings" href="/dashboard/settings" />
        </Sidebar>
        <MainContent>
          {children}  // Page content
        </MainContent>
        <WebSocketHandler />  // Global WS connection
      </Layout>
    </TenantProvider>
  </AuthProvider>
</App>
```

### 7.4 WebSocket Event Types

| Event | Direction | Payload | Trigger |
|-------|-----------|---------|---------|
| `message.new` | Server → Client | `{session_id, message}` | AI/customer sends message |
| `conversation.updated` | Server → Client | `{session_id, status} ` | Status change |
| `escalation.new` | Server → Client | `{session_id, customer, reason}` | Human handover triggered |
| `escalation.resolved` | Server → Client | `{session_id}` | Agent resolved |
| `typing.start` | Server → Client | `{session_id}` | AI typing |
| `typing.stop` | Server → Client | `{session_id}` | AI done typing |
| `campaign.progress` | Server → Client | `{campaign_id, sent, failed}` | Campaign running |

### 7.5 Detailed Page Specs

**Login Page:**
- Auth0 Universal Login or custom JWT form
- On success: redirect to `/switch-tenant` or `/dashboard`
- Role determines redirect destination (admin → switch-tenant, agent → dashboard)

**Tenant Switcher:**
- Required because one user may manage multiple tenants
- Shows tenant name, status, message count
- Select → stores tenant_id in Zustand + localStorage
- After selection → redirect to `/dashboard`

**Live Chat Monitor:**
- WebSocket-powered list of active conversations
- Cards show: customer name, last message preview, sentiment badge, status
- Click card → navigate to `/dashboard/conversation/:id`
- Filter bar: status, sentiment, date range, search by customer name/phone

**Conversation Viewer:**
- Left panel: Message list (scrollable, newest at bottom)
- Right panel: Customer info (name, phone, tags, sentiment history)
- Messages styled as bubbles: customer left-aligned, AI/agent right-aligned
- Human agent can type and send replies (mode switches to "mixed")
- Escalation banner at top if session is escalated

**Broadcast Campaigns:**
- List campaigns with status, schedule, delivery stats
- Create campaign form: name, message content, target audience, schedule
- Campaign analytics: delivery funnel (sent → delivered → read → replied → opt-out)

**Human Escalation Queue:**
- Real-time list of conversations needing human attention
- Each card: customer name, issue summary, sentiment, wait time
- "Claim" button → assigns agent, status changes to "assigned"

---

## STEP 8: Security Layer

### 8.1 X-Hub-Signature-256 Validation

```python
# backend/app/services/whatsapp/webhook_verifier.py

def verify_signature(request: Request, tenant: Tenant) -> bool:
    """
    WhatsApp signs each webhook with HMAC-SHA256 of the raw body.
    We must verify before ANY processing.
    """
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        key=tenant.whatsapp.webhook_secret.encode(),
        msg=request.body,  # Raw bytes, NOT parsed JSON
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)
```

**Critical rules:**
- Use `request.body` (raw bytes), NOT `request.json()` — JSON parsing changes whitespace
- Use `hmac.compare_digest()` — constant-time comparison prevents timing attacks
- Each tenant has a unique webhook secret
- VERIFY BEFORE tenant lookup? No — we need phone_number_id from payload to identify tenant.
  - **Compromise:** First extract phone_number_id, fetch tenant secret, then verify.
  - **Risk window:** 2-3ms between receiving payload and verifying. Acceptable for MVP.
  - **Better approach:** Verify after lookup. If invalid, immediately discard.

### 8.2 JWT Authentication

**Token Structure:**

```json
{
  "sub": "user_uuid",
  "email": "agent@company.com",
  "role": "agent",
  "tenant_ids": ["uuid1", "uuid2"],
  "permissions": ["conversations.read", "messages.send"],
  "iat": 1718888888,
  "exp": 1718975288,
  "iss": "whatsapp-saas"
}
```

**Implementation:**
- Access token: 30 minutes
- Refresh token: 7 days (stored in HTTP-only cookie)
- Use RS256 (asymmetric) — public key in API, private key in auth service
- Blacklist: Store revoked tokens in Redis until they expire

### 8.3 Role-Based Access Control (RBAC)

**Roles and Permissions:**

| Role | Permissions |
|------|-------------|
| `super_admin` | Full access to all tenants, billing, system config |
| `tenant_admin` | Full access within their tenant(s) |
| `agent` | conversations.read, messages.send, escalation.claim |
| `viewer` | conversations.read only |
| `api` | Limited API access with rate limits |

**Enforcement:**

```python
# backend/app/dependencies/auth.py

def require_permission(permission: str):
    async def check(current_user: User = Depends(get_current_user)):
        if permission not in current_user.permissions:
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return check

# Usage:
@router.get("/conversations")
async def list_conversations(
    user: User = Depends(require_permission("conversations.read")),
    tenant: Tenant = Depends(get_current_tenant)
):
    ...
```

### 8.4 Rate Limiting

**Strategy:** Sliding window counter (Redis sorted sets)

| Scope | Limit | Window | Endpoint |
|-------|-------|--------|----------|
| Per tenant (webhook) | 100 requests | 1 second | `/webhook` |
| Per IP (webhook) | 10 requests | 1 second | `/webhook` |
| Per user (API) | 60 requests | 1 minute | `/api/v1/*` |
| Per tenant (messaging) | 80 messages | 1 second | WhatsApp API limit |
| Login attempts | 5 attempts | 15 minutes | `/api/v1/auth/login` |

**Implementation:**

```python
# backend/app/middleware/rate_limit.py

RATE_LIMITS = {
    "webhook_per_tenant": Limit("100/second", scope="tenant:{tenant_id}"),
    "webhook_per_ip": Limit("10/second", scope="ip:{ip}"),
    "api_per_user": Limit("60/minute", scope="user:{user_id}"),
}
```

### 8.5 Secret Management

| Secret | Storage | Access |
|--------|---------|--------|
| WhatsApp Access Tokens | MongoDB (encrypted at rest) + env var for master key | Only tenant service |
| Webhook Secrets | MongoDB (encrypted at rest) | Only webhook verifier |
| JWT Private Key | Environment variable / Secret Manager | Only auth service |
| DB URI | Environment variable | Only connection pool |
| Redis Password | Environment variable | Only connection pool |
| Master Encryption Key | Environment variable / Google Secret Manager | Only startup bootstrap |

**Encryption at rest for tenant secrets:**

```python
from cryptography.fernet import Fernet

# On write:
encrypted_token = Fernet(MASTER_KEY).encrypt(access_token.encode())

# On read:
access_token = Fernet(MASTER_KEY).decrypt(encrypted_token).decode()
```

**Never log secrets.** Use Pydantic's `SecretStr` type — it auto-masks in `__repr__`.

### 8.6 Input Validation

- All request bodies validated via Pydantic models
- WhatsApp webhook payload validated against strict schema (reject unknown fields)
- Phone numbers validated using `phonenumbers` library
- Media URLs validated to be from expected domains only
- MongoDB queries use parameterized syntax (no string interpolation, even with ObjectId)
- All string inputs trimmed and sanitized (no HTML, no control characters except newlines)

### 8.7 Additional Security Measures

- **CORS:** Restricted to dashboard domain only
- **HTTPS:** Enforced at load balancer level (TLS termination)
- **Helmet headers:** Via FastAPI middleware
- **Request size limit:** 10MB max (reject oversized webhooks)
- **WebSocket authentication:** JWT token in query parameter, validated on connect
- **Audit logging:** All security events (login, permission denied, tenant access) logged to `audit_logs`
- **IP allowlisting:** Optional for webhook endpoint (WhatsApp IPs only)

---

## STEP 9: Deployment Architecture

### 9.1 Architecture Overview

```mermaid
%%{init: {'theme': 'dark'}}%%

graph TB
    subgraph "Production Environment"
        subgraph "Google Cloud Run"
            WEB[Webhook Service<br/>FastAPI + Uvicorn<br/>2-10 instances<br/>CPU: 2, RAM: 4GB]
            API[API Service<br/>FastAPI + Uvicorn<br/>2-5 instances]
            WS[WebSocket Service<br/>FastAPI + uvicorn<br/>2-5 instances]
        end
        
        subgraph "Celery Workers (Cloud Run Jobs)"
            W1[Worker 1]
            W2[Worker 2]
            WN[Worker N]
        end
        
        subgraph "Redis (Upstash / Memorystore)"
            RQ[(Task Queue)]
            RC[(Cache)]
        end
        
        subgraph "MongoDB Atlas"
            MDB[(M7 Cluster<br/>3 nodes<br/>Multi-region)]
        end
        
        subgraph "Vercel"
            FE[Next.js Frontend]
        end
        
        subgraph "Object Storage"
            GCS[Google Cloud Storage<br/>Media Files]
        end
        
        subgraph "External"
            WA[WhatsApp Cloud API]
            LLM[OpenAI API]
        end
    end
    
    WA -->|Webhook| WEB
    WEB -->|Enqueue| RQ
    WEB -->|Auth| MDB
    WEB -->|Read| RC
    
    RQ -->|Dequeue| W1
    W1 -->|LangGraph| LLM
    W1 -->|Send Message| WA
    W1 -->|Read/Write| MDB
    W1 -->|Cache| RC
    W1 -->|Upload/Read| GCS
    
    FE -->|REST + WS| API
    API -->|Read| MDB
    API -->|Auth| RC
    API -->|Push Events| WS
    WS --> FE
```

### 9.2 Environment Variables

**Backend:**

```bash
# === Core ===
APP_NAME=whatsapp-ai-saas
ENVIRONMENT=production
LOG_LEVEL=info

# === MongoDB ===
MONGODB_URI=mongodb+srv://cluster0.xxxxx.mongodb.net/
MONGODB_DB_NAME=whatsapp_saas
MONGODB_MAX_POOL_SIZE=100
MONGODB_MIN_POOL_SIZE=10

# === Redis ===
REDIS_URL=rediss://default:xxxxx@xxxxx.upstash.io:6379
REDIS_CACHE_TTL=300

# === Security ===
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...
JWT_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...    # Only in auth service
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
MASTER_ENCRYPTION_KEY=base64_encoded_32_byte_key

# === Celery ===
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}
CELERY_TASK_ALWAYS_EAGER=false    # false in production

# === OpenAI ===
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_MAX_RETRIES=3

# === WhatsApp ===
WHATSAPP_API_VERSION=v21.0
WHATSAPP_BASE_URL=https://graph.facebook.com

# === CORS ===
CORS_ORIGINS=https://dashboard.yourapp.com

# === Observability ===
SENTRY_DSN=https://xxxxx@sentry.io/12345
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318

# === GCP ===
GOOGLE_CLOUD_PROJECT=whatsapp-saas-prod
STORAGE_BUCKET=whatsapp-saas-media
```

**Frontend:**

```bash
NEXT_PUBLIC_API_URL=https://api.yourapp.com
NEXT_PUBLIC_WS_URL=wss://ws.yourapp.com
NEXT_PUBLIC_AUTH0_DOMAIN=your-tenant.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=abc123
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.yourapp.com
```

### 9.3 Docker Architecture

**Backend Dockerfile:**

```dockerfile
# Multi-stage build
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .

# Uvicorn for webhook/API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
```

**Celery Worker Dockerfile:**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["celery", "-A", "workers.celery_app", "worker", "--loglevel=info", "--concurrency=4", "--max-tasks-per-child=100"]
```

**Docker Compose (Local Development):**

```yaml
version: "3.8"
services:
  mongodb:
    image: mongo:7
    ports: ["27017:27017"]
    volumes: [mongodb_data:/data/db]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: .
    ports: ["8080:8080"]
    depends_on: [mongodb, redis]
    environment:
      MONGODB_URI: mongodb://mongodb:27017
      REDIS_URL: redis://redis:6379

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on: [mongodb, redis]
    environment:
      MONGODB_URI: mongodb://mongodb:27017
      REDIS_URL: redis://redis:6379
      CELERY_TASK_ALWAYS_EAGER: "false"

volumes:
  mongodb_data:
```

### 9.4 CI/CD Flow

```mermaid
%%{init: {'theme': 'dark'}}%%
gitGraph
   commit id: "init"
   branch develop
   checkout develop
   commit id: "feat: webhook handler"
   commit id: "feat: langgraph"
   branch feature/campaigns
   commit id: "feat: broadcast"
   checkout develop
   merge feature/campaigns
   branch release/v1.0
   commit id: "chore: bump version"
   checkout main
   merge release/v1.0 tag: "v1.0.0"
   commit id: "deploy: production"
```

**Pipeline Stages (GitHub Actions):**

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pip install -r requirements.txt
      - run: pytest tests/ --cov=app --cov-report=xml
      - run: flake8 app/
      - run: mypy app/

  build-and-push:
    needs: test
    steps:
      - run: docker build -t gcr.io/$PROJECT/webhook:$GITHUB_SHA .
      - run: docker push gcr.io/$PROJECT/webhook:$GITHUB_SHA

  deploy-cloud-run:
    needs: build-and-push
    steps:
      - run: |
          gcloud run deploy webhook \
            --image gcr.io/$PROJECT/webhook:$GITHUB_SHA \
            --platform managed \
            --region us-central1 \
            --min-instances 2 \
            --max-instances 10 \
            --concurrency 80

  deploy-worker:
    needs: build-and-push
    steps:
      - run: |
          gcloud run jobs deploy worker \
            --image gcr.io/$PROJECT/worker:$GITHUB_SHA \
            --tasks 5 \
            --max-retries 3
```

### 9.5 Scaling Configuration

**Cloud Run (Webhook API):**
- Min instances: 2 (keep warm)
- Max instances: 10
- CPU: 2 vCPU
- Memory: 4GB
- Concurrency: 80 requests per instance
- Request timeout: 60s
- Startup CPU boost: true

**Celery Workers (Cloud Run Jobs):**
- Parallelism: 5-20 tasks depending on queue depth
- CPU: 2 vCPU
- Memory: 4GB
- Max retries: 3
- Task timeout: 180s

**MongoDB Atlas:**
- M7 cluster (3 nodes)
- 16GB RAM per node
- 320GB storage
- Multi-region: us-central1 (primary), us-east1 (secondary)

---

## STEP 10: Implementation Roadmap

### Phase 1: Architecture & Database (Week 1)

**Deliverables:**
- [ ] Project scaffolding (folder structure, configs, CI)
- [ ] Docker Compose for local dev (MongoDB, Redis, API skeleton)
- [ ] MongoDB collections created with indexes
- [ ] Pydantic models for all entities
- [ ] Tenant CRUD service
- [ ] `migrations/` directory with index management scripts
- [ ] Audit service (append-only logging)
- [ ] Configuration management (`config.py` with Pydantic Settings)

**Risks:**
- Poor index design leading to slow queries later
- Missing fields in models causing breaking changes

**Mitigation:**
- Design indexes based on actual query patterns (not guesses)
- Use `allow_mutation=False` on frozen models to prevent accidental mutation
- Write integration tests that exercise every index

**Dependencies:** None (greenfield)

**Success Criteria:**
- All 5 collections created with indexes
- Tenant CRUD passing integration tests
- Audit service logging properly
- Docker Compose starts in < 30s

---

### Phase 2: FastAPI Foundation (Week 2)

**Deliverables:**
- [ ] FastAPI app factory with middleware stack
- [ ] Rate limiting middleware (Redis sliding window)
- [ ] Error handler middleware
- [ ] Auth service (JWT issue + verify)
- [ ] RBAC dependency
- [ ] Health check endpoint
- [ ] OpenAPI docs with proper schemas
- [ ] CORS configuration
- [ ] Structured logging (structlog)
- [ ] API v1 router structure

**Risks:**
- JWT implementation vulnerability (weak secret, wrong algorithm)
- CORS misconfiguration

**Mitigation:**
- Use standard library (`python-jose` with RS256)
- Automated CORS testing from different origins
- Security audit of auth flow

**Dependencies:** Phase 1

**Success Criteria:**
- Auth endpoint issues and verifies JWT
- Middleware rate-limits correctly (test with 100 requests in 1s)
- OpenAPI docs render at `/docs`

---

### Phase 3: WhatsApp Integration (Week 2-3)

**Deliverables:**
- [ ] WhatsApp HTTP client with retry logic
- [ ] Text message sender
- [ ] Image message sender
- [ ] Document message sender
- [ ] Read receipt sender
- [ ] Typing indicator (on/off)
- [ ] Media upload endpoint
- [ ] Webhook verification (X-Hub-Signature-256)
- [ ] Mock WhatsApp server for integration tests
- [ ] Rate limit handling for WhatsApp API (429 responses)

**Risks:**
- WhatsApp API rate limits hit during testing
- Media upload failures (large files, wrong format)
- Webhook signature verification bug (body vs JSON)

**Mitigation:**
- Implement exponential backoff for 429s
- Validate media files before upload (size, format, dimensions)
- Write tests that verify signature verification with known test secrets

**Dependencies:** Phase 1

**Success Criteria:**
- All message types send successfully to test phone
- Read receipts work
- Typing indicator appears on WhatsApp
- Mock server passes integration tests

---

### Phase 4: Webhook Processing (Week 3)

**Deliverables:**
- [ ] Webhook receiver endpoint (`POST /webhook`)
- [ ] Tenant resolution from `phone_number_id`
- [ ] Webhook payload schema (validated)
- [ ] Webhook verification middleware
- [ ] BackgroundTasks processing (Phase 1 of async)
- [ ] Message persistence to MongoDB
- [ ] Chat session auto-creation
- [ ] Deduplication (ignore duplicate wam_ids)
- [ ] Webhook verification endpoint (`GET /webhook` for Meta challenge)

**Risks:**
- Duplicate webhooks from WhatsApp (they retry on non-200)
- Webhook processing running longer than 3 seconds
- Missing `wam_id` in some webhook payloads

**Mitigation:**
- Idempotency via `wam_id` unique index (upsert pattern)
- Strict timeout monitoring in BackgroundTasks
- Graceful handling of missing optional fields

**Dependencies:** Phase 3

**Success Criteria:**
- Webhook returns 200 in < 1 second (measured)
- Messages persisted with dedup
- Chat sessions created for new customers
- Meta webhook verification challenge passes

---

### Phase 5: LangGraph (Week 4-5)

**Deliverables:**
- [ ] LangGraph state schema
- [ ] Acknowledge Node (read receipt + typing)
- [ ] Context Retriever Node (history + config)
- [ ] Sentiment Analysis Node
- [ ] LLM Reasoning Node (with structured output)
- [ ] Dispatcher Node (text/image/document routing)
- [ ] Human Handover Node (WebSocket push)
- [ ] Full graph integration test
- [ ] Celery task for processing
- [ ] Error handling + DLQ
- [ ] LangSmith tracing integration

**Risks:**
- LLM response time > 30 seconds (graph timeout)
- LLM returns invalid JSON (structured output parsing fails)
- Sentiment analysis inaccuracy

**Mitigation:**
- Set strict LLM timeout with retry
- Add JSON repair step (attempt to fix malformed JSON)
- Log sentiment accuracy for manual review; fine-tune prompts

**Dependencies:** Phase 2, Phase 4

**Success Criteria:**
- Full graph processes a message in < 60 seconds
- At least 3 different response types sent (text, image, document)
- Human handover triggers correctly for low-confidence inputs
- DLQ captures failed messages

---

### Phase 6: Dashboard (Week 5-7)

**Deliverables:**
- [ ] Next.js project with App Router
- [ ] Auth0 / next-auth integration
- [ ] Zustand stores (auth, conversation, tenant)
- [ ] Login page
- [ ] Tenant Switcher page
- [ ] Dashboard layout with sidebar
- [ ] Live Chat Monitor (WebSocket)
- [ ] Conversation Viewer page
- [ ] Broadcast Campaign CRUD
- [ ] Human Escalation Queue
- [ ] Settings page
- [ ] WebSocket server (FastAPI)
- [ ] Media preview component

**Risks:**
- WebSocket scaling (sticky sessions needed for multi-instance)
- Real-time lag under heavy load

**Mitigation:**
- Use Redis Pub/Sub for cross-instance WebSocket events
- Implement message batching for high-frequency updates
- Consider moving to Socket.IO if native WS proves insufficient

**Dependencies:** Phase 1, Phase 5

**Success Criteria:**
- Dashboard displays real-time conversations
- Agent can send messages from dashboard
- Escalation queue updates in real-time
- Campaigns can be created, scheduled, and monitored

---

### Phase 7: Deployment (Week 7-8)

**Deliverables:**
- [ ] Docker images for API + worker
- [ ] Cloud Run deployment configuration
- [ ] MongoDB Atlas cluster setup
- [ ] Redis (Upstash) setup
- [ ] GitHub Actions CI/CD pipeline
- [ ] Environment configuration per stage (dev/staging/prod)
- [ ] Sentry error tracking
- [ ] Prometheus metrics endpoint
- [ ] Logging aggregation (Cloud Logging)
- [ ] Load testing (k6)
- [ ] Disaster recovery plan
- [ ] Runbooks created

**Risks:**
- Cloud Run cold start for webhook (needs < 50ms)
- MongoDB connection pooling issues under load
- Secrets leaked in CI/CD logs

**Mitigation:**
- Set min instances = 2 (no cold starts)
- Use connection pooling with proper min/max pool sizes
- Use GitHub Actions secrets (never env vars in YAML)
- Pre-warm connections on startup

**Dependencies:** Phase 1-6

**Success Criteria:**
- Webhook endpoint responds in < 500ms P99 (including cold start) — wait, with min instances it should be fine
- Load test: 1000 webhooks/minute with < 1% error rate
- Dashboard loads in < 2 seconds
- CI/CD pipeline completes in < 10 minutes

---

## Architecture Decision Records

### ADR-001: Why Celery (not just FastAPI BackgroundTasks)

**Status:** Accepted (for MVP + migration path)

**Context:** Webhook needs < 3s response. LangGraph takes 10-30s.

**Options:**
1. FastAPI BackgroundTasks — zero infra, but no persistence/retries
2. Celery + Redis — production-ready, but needs Redis + worker deployment
3. Redis Queue (RQ) — simpler than Celery, but less features
4. Google Cloud Tasks — managed, but vendor lock-in

**Decision:** Start with BackgroundTasks for MVP (zero infra, 1-2 tenants). Add Celery in Phase 5 when:
- Tenants > 3
- Workers need independent scaling
- Broadcast campaigns require scheduling
- Task monitoring is required

### ADR-002: Why MongoDB (not PostgreSQL)

**Status:** Accepted

**Context:** We need a document store for flexible message schemas, media metadata, and nested tenant config.

**Reasons:**
- Message content varies (text vs image vs document vs future types) — documents fit MongoDB
- Nested tenant config (hours, thresholds, media library) — flat tables would need EAV pattern
- Scaling: MongoDB native sharding on `tenant_id`
- Atlas search for future vector capabilities
- Auto-TTL for audit logs and closed sessions

**But:** If you need complex aggregations (JOINs across sessions, customers, campaigns), PostgreSQL would be better. For this use case, MongoDB is the right call.

### ADR-003: Why LangGraph (not a simple chain/agent)

**Status:** Accepted

**Context:** The workflow has conditional branching, human-in-the-loop, and needs to be observable.

**Decision:** LangGraph provides state machine structure that's testable, debuggable, and extensible. A simple chain would work for Phase 1 but require a painful refactor later.

### ADR-004: Why async message sending (not synchronous webhook response)

**Status:** Non-negotiable

**Context:** WhatsApp expects 200 OK within 3 seconds of webhook delivery.

**Decision:** The webhook response is purely an acknowledgment. The actual AI reply is sent as a separate WhatsApp API call 10-30 seconds later. This is NOT a design preference — it's a hard constraint of the WhatsApp API and LLM latency. Any architecture that tries to reply synchronously is fundamentally flawed.

---

## Appendix: Error Codes

| Code | Meaning | HTTP Status |
|------|---------|-------------|
| `TENANT_NOT_FOUND` | phone_number_id not in any tenant | 404 |
| `TENANT_PAUSED` | Tenant is in paused/suspended state | 503 |
| `INVALID_SIGNATURE` | X-Hub-Signature-256 mismatch | 401 |
| `RATE_LIMITED` | Too many requests | 429 |
| `INVALID_MEDIA` | Media file is invalid format/size | 422 |
| `WHATSAPP_API_ERROR` | WhatsApp API returned error | 502 |
| `LLM_TIMEOUT` | LLM call exceeded timeout | 504 |
| `INVALID_JWT` | JWT expired or malformed | 401 |
| `INSUFFICIENT_PERMISSIONS` | Role lacks required permission | 403 |
| `DUPLICATE_MESSAGE` | wam_id already processed | 409 |

---

## Appendix: Key Metrics to Track

| Metric | Where | Alert Threshold |
|--------|-------|----------------|
| Webhook latency (p95) | FastAPI metrics | > 1s |
| Webhook error rate | FastAPI metrics | > 1% |
| LangGraph completion rate | Redis counter | < 95% |
| LangGraph duration (p95) | LangSmith | > 45s |
| Queue depth | Redis | > 1000 |
| Worker utilization | Cloud Run | > 80% CPU |
| MongoDB query latency (p95) | Atlas metrics | > 100ms |
| WhatsApp API error rate | Service metrics | > 2% |
| LLM token usage/hour | LangSmith | Budget threshold |
| Sentiment drop rate | MongoDB agg | > 10% negative |
| Human handover rate | MongoDB agg | > 30% / tenant |
