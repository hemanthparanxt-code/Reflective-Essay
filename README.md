# Aurora Reflective Essay Evaluator

This project evaluates student reflective essay PDFs using the Google Gemini API, and provides a browser console script to fill scores into the Aurora Faculty Portal.

---

## 🚀 Deploying to Render (Cloud Backend)

Deploying to [Render](https://render.com) gives you a public HTTPS URL (e.g., `https://aurora-essay-evaluator.onrender.com`), eliminating the need to run Python locally.

### Step 1: Push or Upload to GitHub
1. Create a repository on GitHub (public or private).
2. Push this project code to your repository:
   ```bash
   git init
   git add .
   git commit -m "Aurora Evaluator Render setup"
   git remote add origin https://github.com/YOUR_USERNAME/aurora_reflective_essay_evaluator.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Create a Web Service on Render
1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** > **Web Service**.
3. Connect your GitHub repository.
4. Fill in the service configuration:
   - **Name:** `aurora-essay-evaluator` (or any name you choose)
   - **Region:** Choose the region closest to you (e.g., Singapore, Oregon, Frankfurt)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 2
     ```
   - **Instance Type:** `Free`

### Step 3: Set Environment Variables on Render
Scroll down to the **Environment Variables** section in Render and add:
- `GEMINI_API_KEY`: Paste your Gemini API key (from [Google AI Studio](https://aistudio.google.com/app/apikey))
- `GEMINI_MODEL`: `gemini-2.5-flash` (optional, defaults to `gemini-2.5-flash`)
- `PYTHON_VERSION`: `3.11.9` (optional)

### Step 4: Deploy and Verify
1. Click **Deploy Web Service**.
2. Wait 1–2 minutes for the build to finish.
3. Once the status shows **Live**, open your service URL in your browser:
   - Root URL: `https://your-service-name.onrender.com/` → will show `status: online`
   - Health URL: `https://your-service-name.onrender.com/health` → will show `ok: true`, `api_key_configured: true`

---

## 💻 Running the Browser Automation (`aurora_console.js`)

1. Open `aurora_console.js`.
2. Update line 19 with your Render URL:
   ```javascript
   BACKEND: "https://your-service-name.onrender.com/evaluate",
   ```
3. Open the Aurora Faculty Portal Evaluate page in Chrome/Edge/Firefox.
4. Press `F12` to open DevTools, switch to the **Console** tab.
5. Paste the contents of `aurora_console.js` and press Enter.

### Safety Modes
- **`DRY_RUN: true` (default):** Evaluates submissions and outputs question scores & feedback into DevTools console without entering or saving any points.
- **`AUTO_SAVE_NEXT: false` (default):** When you set `DRY_RUN: false`, it fills the score for the current student only, allowing you to manually verify the score before advancing.
- Once confident after reviewing several students, you can enable `AUTO_SAVE_NEXT: true`.

> **Note on Render Free Tier:**
> Free tier instances spin down after 15 minutes of inactivity. When you open the portal, the first request may take 30–50 seconds while Render wakes the container up. You can open `https://your-service-name.onrender.com/health` in a browser tab beforehand to wake it up instantly.

---

## 🛠 Local Setup (Optional Alternative)

If you prefer running locally on your own machine instead of Render:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GEMINI_API_KEY="YOUR_KEY"
python app.py
```
And set `BACKEND: "http://127.0.0.1:8765/evaluate"` in `aurora_console.js`.
