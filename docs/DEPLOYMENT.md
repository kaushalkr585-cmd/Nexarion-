# Deployment Guide — Render (Backend) + Vercel (Frontend)

Free-tier deployment using Render for the FastAPI backend and Vercel for the React frontend. Costs and free-tier limits depend on provider policies and usage.

---

## Architecture

```
User Browser
     │
     ▼
┌─────────────┐    Vercel Edge Rewrites     ┌──────────────────┐
│   Vercel    │  ──────/api/*──────────────▶ │  Render (Free)   │
│  Frontend   │                              │  FastAPI Backend  │
│  (React)    │                              │                  │
└─────────────┘                              └──────┬───────────┘
                                                    │
                              ┌──────────────────────┼──────────────────┐
                              ▼                                         ▼
                     ┌────────────────┐                      ┌──────────────────┐
                     │ Neon / Supabase│                      │  NVIDIA NIM API  │
                     │  PostgreSQL    │                      │  (Cloud AI)      │
                     │  (Free)        │                      │  (Free Credits)  │
                     └────────────────┘                      └──────────────────┘
```

---

## Prerequisites

- GitHub account (repository pushed to GitHub)
- Free accounts on: [Vercel](https://vercel.com), [Render](https://render.com), [Neon](https://neon.tech)
- [NVIDIA NIM API key](https://build.nvidia.com) (free tier)

---

## Step 1: Create Free PostgreSQL Database (Neon)

Render's free Postgres expires after 30 days. Use an external database such as **Neon** if you need data to outlast that limit.

1. Go to [neon.tech](https://neon.tech) and sign up (no credit card).
2. Click **New Project** → Name it `nexarion`.
3. Copy the connection string. It looks like:
   ```
   postgresql://user:password@ep-cool-name-123456.us-east-2.aws.neon.tech/nexarion_db?sslmode=require
   ```
4. Change the driver prefix from `postgresql://` to `postgresql+psycopg://`:
   ```
   postgresql+psycopg://user:password@ep-cool-name-123456.us-east-2.aws.neon.tech/nexarion_db?sslmode=require
   ```

---

## Step 2: Get Free NVIDIA NIM API Key

1. Go to [build.nvidia.com](https://build.nvidia.com).
2. Sign up for free and generate an API key.
3. Save the key (starts with `nvapi-`).

---

## Step 3: Deploy Backend to Render

### Option A: One-Click Blueprint (Fastest)

1. Go to [render.com/deploy](https://render.com/deploy).
2. Point it to your GitHub repository.
3. Render reads `render.yaml` and creates the service automatically.
4. Set the environment variables marked `sync: false` in the Render dashboard.

### Option B: Manual Setup

1. Go to [render.com](https://render.com) → **New** → **Web Service**.
2. Connect your GitHub repository.
3. Configure:
   - **Name**: `nexarion-backend`
   - **Region**: Choose closest to you
   - **Runtime**: **Docker**
   - **Instance Type**: **Free**
4. Add environment variables:

| Variable | Value |
|---|---|
| `APP_NAME` | `nexarion` |
| `LOG_LEVEL` | `INFO` |
| `DEBUG` | `false` |
| `SESSION_SECRET` | *(click Generate)* |
| `DATABASE_URL` | *(your Neon connection string from Step 1)* |
| `FRONTEND_URL` | *(fill after Vercel deploy, e.g. `https://nexarion.vercel.app`)* |
| `LLM_PROVIDER` | `nvidia` |
| `NVIDIA_API_KEY` | *(your key from Step 2)* |
| `NVIDIA_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` |

5. Click **Deploy**.
6. Wait for the build to finish. Note your backend URL (e.g. `https://nexarion-backend.onrender.com`).
7. Verify: visit `https://nexarion-backend.onrender.com/health`.

---

## Step 4: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project**.
2. Import your GitHub repository.
3. Configure:
   - **Root Directory**: `frontend`
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add environment variable:

| Variable | Value |
|---|---|
| `BACKEND_URL` | `https://nexarion-backend.onrender.com` |

5. Click **Deploy**.
6. Note your frontend URL (e.g. `https://nexarion.vercel.app`).

---

## Step 5: Connect Frontend ↔ Backend

1. Go back to **Render Dashboard** → your backend service → **Environment**.
2. Set `FRONTEND_URL` to your Vercel URL (e.g. `https://nexarion.vercel.app`).
3. Click **Save Changes** (Render will redeploy automatically).

---

## Step 6: Prevent Render from Sleeping (UptimeRobot)

Render free tier sleeps after 15 minutes of inactivity. Use a free pinger to keep it alive.

1. Go to [uptimerobot.com](https://uptimerobot.com) and create a free account.
2. Click **Add New Monitor**:
   - **Monitor Type**: `HTTP(s)`
   - **URL**: `https://nexarion-backend.onrender.com/health`
   - **Monitoring Interval**: `5 minutes`
3. A successful health request every five minutes can prevent the 15-minute idle timeout while checks are running. This does not guarantee continuous availability: Render may restart free services, and free plans have usage limits.

---

## Local Development

For local development with Docker and NVIDIA NIM:

```bash
docker compose up --build -d
```

Set `NVIDIA_API_KEY` in `.env` before starting. Ollama is no longer included in Docker Compose; to use local inference, run Ollama separately and configure the backend to reach it.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| CORS errors in browser | Ensure `FRONTEND_URL` on Render matches your exact Vercel URL (including `https://`) |
| "Model isn't configured" | Verify `NVIDIA_API_KEY` is set correctly on Render |
| Database connection fails | Ensure Neon connection string uses `postgresql+psycopg://` prefix and includes `?sslmode=require` |
| Render service sleeps | Check the monitor; free services can still restart and are not guaranteed to stay online |
| Frontend API calls fail | Check that `BACKEND_URL` environment variable is set in Vercel project settings |
