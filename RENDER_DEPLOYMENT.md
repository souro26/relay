# Deploying Relay on Render (Free Tier)

This guide covers deploying Relay to **[Render](https://render.com/)** using Render's 100% free tier.

---

## 1. Architecture Overview

Render's free tier provides:
- **1 Free Web Service** (512 MB RAM, shared CPU)
- **1 Free PostgreSQL Database** (1 GB storage)

To keep the entire architecture 100% free with zero cloud bills, Relay bundles the simulated `order_service` into the same Docker container when deployed on Render:

```
                  Internet / Browser
                          │
                          ▼ (Port 443 / $PORT)
           ┌───────────────────────────────┐
           │   Render Free Web Service     │
           │                               │
           │  ┌─────────────────────────┐  │
           │  │   Relay API & Web UI    │  │
           │  │   (uvicorn :$PORT)      │  │
           │  └───────────┬─────────────┘  │
           │              │                │
           │              ▼ (internal)     │
           │  ┌─────────────────────────┐  │
           │  │ Simulated Order Service │  │
           │  │ (uvicorn 127.0.0.1:8001)│  │
           │  └─────────────────────────┘  │
           └──────────────┬────────────────┘
                          │
                          ▼ (Managed Connection)
           ┌───────────────────────────────┐
           │ Render Free Managed Postgres  │
           │          (relay-db)           │
           └───────────────────────────────┘
```

- When `START_INTERNAL_ORDER_SERVICE=true`, `docker/entrypoint.sh` starts `order_service` on `127.0.0.1:8001` in the background.
- `ORDER_SERVICE_URL` is set to `http://127.0.0.1:8001`, so Relay communicates with it locally inside the container without incurring costs for a second web service.
- Database migrations (`alembic upgrade head`) execute automatically on container startup when `RUN_MIGRATIONS=true`.

---

## 2. Option A: Blueprint Deployment (Recommended, 2 Minutes)

Render Blueprints let you deploy the database and web service simultaneously from the included `render.yaml` file:

1. **Push your code to GitHub**:
   Ensure your changes are committed and pushed to your GitHub repository:
   ```bash
   git push origin main
   ```

2. **Log into Render**:
   - Go to [dashboard.render.com](https://dashboard.render.com/).
   - Click **New +** in the top navigation bar.
   - Select **Blueprint**.

3. **Connect Your Repository**:
   - Select your `souro26/relay` repository.
   - Render will detect `render.yaml` in the root directory.
   - Click **Apply**.

4. **Render handles the rest**:
   - Provisions the PostgreSQL database (`relay-db`).
   - Builds the Docker image from `docker/Dockerfile`.
   - Links `DATABASE_URL` from the database directly into the web service.
   - Runs Alembic database migrations.
   - Starts Relay and assigns a public URL: `https://<service-name>.onrender.com`.

---

## 3. Option B: Manual Dashboard Deployment

If you prefer to configure services manually via the Render UI:

### Step 1: Create Free PostgreSQL Database
1. In Render Dashboard, click **New +** → **PostgreSQL**.
2. Name: `relay-db`
3. Database: `relay`
4. User: `relay`
5. Region: Oregon (or closest to you)
6. Plan: **Free**
7. Click **Create Database**.
8. Once created, copy the **Internal Database URL** (e.g., `postgres://relay:...@dpg-...:5432/relay`).

### Step 2: Create Web Service
1. Click **New +** → **Web Service**.
2. Connect your GitHub repository (`relay`).
3. Settings:
   - **Name**: `relay`
   - **Language**: **Docker**
   - **Dockerfile Path**: `docker/Dockerfile`
   - **Docker Context**: `.`
   - **Region**: Same region as database (e.g. Oregon)
   - **Instance Type**: **Free**
4. Expand **Advanced** and configure Environment Variables:

| Key | Value | Description |
|---|---|---|
| `DATABASE_URL` | *(paste Internal Database URL)* | Render Postgres connection string |
| `ORDER_SERVICE_URL` | `http://127.0.0.1:8001` | Local simulated order service |
| `START_INTERNAL_ORDER_SERVICE` | `true` | Runs order service inside container |
| `RUN_MIGRATIONS` | `true` | Runs `alembic upgrade head` on boot |
| `LLM_PROVIDER` | `openai` *(or `nvidia`)* | Supported LLM provider |
| `OPENAI_API_KEY` | *(optional)* | Only required if `LLM_PROVIDER=openai` |
| `LOG_LEVEL` | `INFO` | Standard structured logging |
| `APP_ENV` | `production` | Production environment flag |

5. Under **Health Check Path**, enter: `/health`
6. Click **Create Web Service**.

---

## 4. Free Tier Considerations & Best Practices

1. **Spin-down after inactivity (Cold Starts)**:
   - Render's free tier spins down the web service after 15 minutes of inactivity.
   - The first request after spin-down may take ~30–50 seconds to wake the container.
   - Subsequent requests are immediate.

2. **Free Database Expiry**:
   - Render free tier databases expire 30 days after creation.
   - For a permanent hobby database, you can connect an external free PostgreSQL database (e.g., [Neon.tech](https://neon.tech/) or [Supabase](https://supabase.com/)) by simply updating the `DATABASE_URL` environment variable.

3. **Live Health Checks**:
   - Liveness probe: `GET https://your-app.onrender.com/health` (HTTP 200)
   - Readiness probe: `GET https://your-app.onrender.com/ready` (checks DB & downstream order service connectivity)

---

## 5. Verifying Deployment

Once Render displays **Deploy live**:
1. Open `https://your-app.onrender.com/` in your browser.
2. Confirm the **System Status: Healthy** badge is green in the header.
3. Test natural language workflows:
   - Navigate to **New Request** (`/workflows/new`).
   - Click one of the example prompt chips (e.g., *"Delay order ORD-1002 by 7 days due to supplier backlog"*).
   - Click **Run Integrated Workflow**.
   - Watch the interactive visual step pipeline run through validation, order lookup, customer verification, and execution!
