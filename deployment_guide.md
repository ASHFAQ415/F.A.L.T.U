# 🤡 F.A.L.T.U — Complete Deployment Guide

> Follow these steps **in order** after your code is pushed to GitHub.
> Total time: ~10 minutes.

---

## ✅ Prerequisites (Do These First)

### 1. Get a Free Groq API Key
1. Go to **[console.groq.com](https://console.groq.com)**
2. Sign up (free, no credit card needed)
3. Click **API Keys** in the left sidebar
4. Click **Create API Key** → give it a name like "faltu"
5. **Copy the key** (starts with `gsk_...`) — save it somewhere, you'll need it in Step 5

### 2. Generate a JWT Secret
Open PowerShell and run this:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
**Copy the output** — this is your JWT secret. Save it, you'll need it in Step 5.

---

## 🚀 Railway Deployment (Step by Step)

### Step 1 — Create a Railway Account
1. Go to **[railway.app](https://railway.app)**
2. Click **Login** → **Login with GitHub**
3. Authorize Railway to access your GitHub account
4. You'll land on the Railway dashboard

---

### Step 2 — Create a New Project
1. Click the purple **+ New Project** button (top right)
2. Select **Deploy from GitHub repo**
3. If Railway asks to install the GitHub App, click **Configure** and give it access to your `F.A.L.T.U` repository
4. Select **`ASHFAQ415/F.A.L.T.U`** from the list
5. Railway will create a service and immediately try to build — **it will fail** (that's OK, we need to configure it first)

---

### Step 3 — Configure the Backend Service
1. Click on the service block that was just created (it should say "F.A.L.T.U" with a failed status)
2. Click the **Settings** tab at the top of the panel
3. Scroll down to find **Root Directory** (under Source section)
4. Change it from `/` to:
   ```
   backend
   ```
5. *(Optional)* Scroll to the top → click the service name → rename it to `backend`
6. **Don't redeploy yet** — we need to add variables first

---

### Step 4 — Add PostgreSQL Database
1. Click the **+ New** button on the Railway project canvas (top right of the canvas, NOT the service panel)
2. Select **Database** → **Add PostgreSQL**
3. Railway will create a PostgreSQL instance and automatically inject `DATABASE_URL` into all services
4. **That's it!** No configuration needed for the database

---

### Step 5 — Set Backend Environment Variables
1. Click on your **backend** service block
2. Click the **Variables** tab
3. Click **+ New Variable** and add these one by one:

| Variable | Value |
|----------|-------|
| `GROQ_API_KEY` | `gsk_...` *(the key you copied from console.groq.com)* |
| `JWT_SECRET_KEY` | *(the random string you generated with Python)* |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | *(choose a strong password, e.g. `MyFaltu@2024!`)* |
| `ADMIN_EMAIL` | `your-email@example.com` |
| `DATA_DIR` | `/app/data` |
| `CHROMA_DATA_DIR` | `/app/data/chroma` |

4. After adding all variables, Railway will automatically trigger a new build

---

### Step 6 — Wait for Backend to Build ☕
1. Go back to the **Deployments** tab of the backend service
2. You should see a new deployment building
3. **This will take 5-10 minutes** (it's downloading ML models: sentence-transformers + cross-encoder + spaCy)
4. Wait until the status shows **✅ Success**

> [!IMPORTANT]
> If the build fails, click **View logs** to see the error. Common issues:
> - Missing `GROQ_API_KEY` → go back to Variables and add it
> - Memory limit → Railway free tier has 512MB RAM, which is tight. The build should work but if it doesn't, try upgrading to the Hobby plan ($5/month)

---

### Step 7 — Generate a Public URL for the Backend
1. Click on the **backend** service block
2. Click the **Settings** tab
3. Scroll down to **Networking** section
4. Under **Public Networking**, click **Generate Domain**
5. Railway will generate a URL like: `backend-production-xxxx.up.railway.app`
6. **Copy this URL** — you'll need it for the frontend

---

### Step 8 — Create the Frontend Service
1. Go back to the Railway project canvas (click the project name at the top)
2. Click **+ New** → **GitHub Repo**
3. Select the same **`ASHFAQ415/F.A.L.T.U`** repository again
4. A second service block will appear on the canvas

---

### Step 9 — Configure the Frontend Service
1. Click on the **new** service block
2. Go to **Settings** tab
3. Change **Root Directory** to:
   ```
   frontend
   ```
4. *(Optional)* Rename the service to `frontend`

---

### Step 10 — Set Frontend Environment Variables
1. Click on the **frontend** service block
2. Click the **Variables** tab
3. Add this variable:

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | `https://backend-production-xxxx.up.railway.app` *(the URL from Step 7 — include `https://`)* |

4. Railway will trigger a build for the frontend

---

### Step 11 — Generate a Public URL for the Frontend
1. Click on the **frontend** service block
2. Click **Settings** tab
3. Scroll to **Networking** → **Public Networking** → **Generate Domain**
4. You'll get a URL like: `frontend-production-xxxx.up.railway.app`
5. **This is your public chatbot URL!** 🎉

---

### Step 12 — Test It! 🤡
1. Open the frontend URL in your browser
2. You should see the F.A.L.T.U login page with the 🤡 logo
3. Log in with:
   - **Username:** `admin` (or whatever you set in `ADMIN_USERNAME`)
   - **Password:** *(whatever you set in `ADMIN_PASSWORD`)*
4. Upload a document in the **📄 Docs** page
5. Ask questions about it in the **💬 Chat** page
6. **Share the URL with anyone** — they can access it from any browser!

---

## 🎯 Quick Checklist

```
[ ] Groq API key from console.groq.com
[ ] Railway account (login with GitHub)
[ ] Created project from F.A.L.T.U repo
[ ] Backend service: Root Directory = backend
[ ] Added PostgreSQL database
[ ] Backend variables: GROQ_API_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD, etc.
[ ] Backend: Generated public domain URL
[ ] Frontend service: Root Directory = frontend
[ ] Frontend variable: BACKEND_URL = https://your-backend-url.railway.app
[ ] Frontend: Generated public domain URL
[ ] Logged in and tested! 🤡
```

---

## 🛠️ If Something Goes Wrong

| Problem | Solution |
|---------|----------|
| Build fails with "memory" error | Railway free tier has 512MB limit. Try the Hobby plan ($5/mo) or remove `spacy` and PII detection from requirements |
| "Cannot connect to backend" on login | Check that `BACKEND_URL` in frontend variables has `https://` prefix and matches the backend's generated domain |
| "Groq API unavailable" | Verify `GROQ_API_KEY` is set correctly in backend variables (starts with `gsk_`) |
| Frontend shows but backend returns 500 | Click backend service → Deployments → View logs to see the actual error |
| GitHub Actions still failing (red X) | That's fine! Railway deploys directly from GitHub, you don't need the GitHub Action. You can delete `.github/workflows/deploy.yml` if the red X bothers you |

---

> [!TIP]
> **Every time you `git push` to the `main` branch**, Railway will automatically rebuild and redeploy both services. No manual action needed after the initial setup!
