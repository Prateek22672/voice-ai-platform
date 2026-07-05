# Deploy the Voice AI service (so everyone can test it live, 24/7)

Goal: one public URL your manager & employees can open to test the full experience. The whole stack
is Docker, so deploying = copy the folder to a cloud VM and run **one command**.

---

## Pick where to run it

| Option | Cost | Notes |
|---|---|---|
| **A. Oracle Cloud "Always Free" VM** | **₹0 forever** | Ampere ARM, up to 4 CPU / **24 GB RAM** — runs the FULL stack (Kokoro TTS included). Best free. |
| **B. Small VPS** (Hetzner / DigitalOcean) | ~₹350–800/mo | x86, zero friction, 5-min setup. Becomes your production box later. |

Both use the **same steps** below. Recommended: **A for free**, **B if you want it in 5 minutes.**

---

## The process (same for A or B) — ~20–30 min

### 1. Create the VM
- **Oracle (A):** oracle.com/cloud/free → create an *Always Free* **Ampere (ARM) VM**, Ubuntu 22.04,
  4 OCPU / 24 GB RAM. Note its **public IP**.
- **VPS (B):** create an Ubuntu 22.04 server, 4 GB+ RAM. Note its **public IP**.

### 2. Open the ports (cloud firewall / security list)
Allow inbound TCP: **3000, 8000, 8001, 8002, 8080** (the website + the APIs).
- Oracle: VCN → Security List → add Ingress rules for those ports (source `0.0.0.0/0`).
- VPS: usually open by default; if using `ufw`: `sudo ufw allow 3000,8000,8001,8002,8080/tcp`.

### 3. Install Docker on the VM
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # then log out & back in
```

### 4. Get the project onto the VM
Easiest: push this repo to GitHub, then on the VM:
```bash
git clone <your-repo-url> voice-ai && cd voice-ai
```
Or copy it directly from your PC:
```bash
# from your Windows machine (PowerShell), replace IP:
scp -r "C:\My Projects\voice-ai\voice-ai-platform" ubuntu@<VM-IP>:~/voice-ai
```

### 5. Create the `.env` on the VM
```bash
cp .env.example .env    # then edit .env and set:
#   GROQ_API_KEY=gsk_...            (your Groq key — STT + LLM)
#   OPENAI_API_KEY=sk-...           (optional fallback)
#   STT_BACKEND=groq                (fast, cheap, accurate)
#   ADMIN_PASSWORD=<something strong>
```
Never commit `.env` (it's gitignored).

### 6. Launch the whole stack — one command
```bash
docker compose up -d --build
```
First build downloads models (~a few minutes). Check it:
```bash
docker compose ps
curl http://localhost:8001/health
```

### 7. Share the URL
Open **`http://<VM-PUBLIC-IP>:3000`** — that's the live site. Send it to your manager/employees.
They can use **Talk to Agent**, **Insights**, and you the **Admin** panel — all pointing at the VM
automatically (the frontend is host-aware).

For your interview platform, its API base becomes **`http://<VM-PUBLIC-IP>:8080`** with the key from Admin.

---

## Optional (recommended before a real launch): one clean HTTPS URL
Instead of exposing 5 ports, put **Caddy** in front for `https://voice.yourdomain.com`:
```
# Caddyfile (auto-HTTPS)
voice.yourdomain.com {
    reverse_proxy /v1/stt*  localhost:8001
    reverse_proxy /v1/tts*  localhost:8002
    reverse_proxy /v1/*     localhost:8080
    reverse_proxy /ws*      localhost:8000
    reverse_proxy *         localhost:3000
}
```
`sudo apt install caddy` → point your domain's DNS at the VM IP → done (free TLS).
Mic access (`getUserMedia`) requires **HTTPS** on public URLs, so this step is needed for the browser
voice demo to work for remote users — do it before wide sharing.

---

## Quick reference
- Start / update: `docker compose up -d --build`
- Logs: `docker compose logs -f stt-service`
- Stop: `docker compose down`  ·  Restart one: `docker compose restart dashboard`
- The `.env` holds all secrets; ports are set in `docker-compose.yml`.
