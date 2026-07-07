"""Telephony Service — Asterisk ARI controller + REST API for calls.
Replaces Twilio's voice API. Asterisk handles SIP/RTP; this app drives it over ARI.

POST /v1/calls                : originate outbound call {"to": "+1555...", "agent_prompt": "..."}
GET  /v1/calls/{id}           : call status
POST /v1/calls/{id}/hangup

Flow (inbound + outbound identical after answer):
  Asterisk StasisStart -> answer -> externalMedia (RTP<->this app) ->
  bridge audio to websocket-gateway agent session -> TTS audio back into call.
Audio bridge: Asterisk externalMedia sends RTP (slin16) to UDP port here; we strip RTP
headers, forward PCM to gateway WS, and return agent PCM as RTP back."""
import asyncio, audioop, json, os, socket, struct, sys, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import httpx, websockets
from fastapi import FastAPI, Depends, HTTPException
from shared.auth import verify_api_key

app = FastAPI(title="telephony-service", version="1.0.0")

ARI_URL  = os.getenv("ARI_URL", "http://asterisk:8088")
ARI_AUTH = (os.getenv("ARI_USER", "voiceai"), os.getenv("ARI_PASSWORD", "voiceai-ari-secret"))
GW_WS    = os.getenv("GW_WS", "ws://websocket-gateway:8000/v1/agent/stream")
# asterisk runs on the HOST network; it reaches our RTP socket via the published host port,
# so the externalMedia target is 127.0.0.1:<port> from asterisk's point of view.
EXTERNAL_MEDIA_HOST = os.getenv("EXTERNAL_MEDIA_HOST", "127.0.0.1")
RTP_PORT_BASE = int(os.getenv("RTP_PORT_BASE", "18000"))
VOICE_DIR = os.getenv("VOICE_DIR", "./voices")
# Cost control: calls auto-hang-up at this limit. Default 5 min; callers can pick less,
# and MAX_CALL_HARD_CAP_S is the ceiling nobody can exceed from the UI.
MAX_CALL_S = int(os.getenv("MAX_CALL_S", "300"))
MAX_CALL_HARD_CAP_S = int(os.getenv("MAX_CALL_HARD_CAP_S", "1800"))

CALLS: dict[str, dict] = {}

def _save_call(call_id: str):
    """Persist the full call record (status + transcript) so it survives restarts."""
    c = CALLS.get(call_id)
    if not c:
        return
    try:
        os.makedirs(VOICE_DIR, exist_ok=True)
        rec = {k: v for k, v in c.items() if not k.startswith("_")}
        rec["call_id"] = call_id
        with open(os.path.join(VOICE_DIR, f"call_{call_id}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

def _load_saved_calls() -> dict:
    """Merge on-disk call records (older runs) with in-memory ones."""
    out = {}
    try:
        for fn in os.listdir(VOICE_DIR):
            if fn.startswith("call_") and fn.endswith(".json"):
                try:
                    rec = json.load(open(os.path.join(VOICE_DIR, fn), encoding="utf-8"))
                    out[rec.get("call_id", fn[5:-5])] = rec
                except Exception:
                    continue
    except Exception:
        pass
    return out

@app.get("/health")
def health():
    return {"ok": True, "service": "telephony"}

@app.post("/v1/calls")
async def originate(body: dict, tenant=Depends(verify_api_key)):
    to = body.get("to")
    if not to:
        raise HTTPException(400, "'to' required (E.164)")
    call_id = str(uuid.uuid4())
    async with httpx.AsyncClient(auth=ARI_AUTH, timeout=30) as c:
        r = await c.post(f"{ARI_URL}/ari/channels", params={
            "endpoint": f"PJSIP/{to}@telnyx-trunk",
            "app": "voiceai",
            "appArgs": call_id,
            "callerId": os.getenv("SIP_DID_NUMBER", "anonymous"),
        })
        if r.status_code >= 300:
            raise HTTPException(502, f"ARI originate failed: {r.text}")
        ch = r.json()
    try:
        limit = int(body.get("max_duration_s") or MAX_CALL_S)
    except Exception:
        limit = MAX_CALL_S
    limit = max(30, min(limit, MAX_CALL_HARD_CAP_S))
    CALLS[call_id] = {"status": "dialing", "channel_id": ch["id"], "to": to,
                      "agent_prompt": body.get("agent_prompt", ""),
                      "greeting_prompt": body.get("greeting_prompt", ""),
                      "scenario": body.get("scenario", "custom"),
                      "max_duration_s": limit,
                      "transcript": [],
                      "tenant_id": tenant["tenant_id"], "started": time.time()}
    return {"call_id": call_id, "status": "dialing", "max_duration_s": limit}

@app.get("/v1/calls")
async def list_calls(tenant=Depends(verify_api_key)):
    """All calls (live + saved), newest first, with a transcript preview count."""
    merged = _load_saved_calls()
    for cid, c in CALLS.items():
        merged[cid] = {**merged.get(cid, {}), **{k: v for k, v in c.items() if not k.startswith("_")},
                       "call_id": cid}
    items = []
    for cid, c in merged.items():
        items.append({"call_id": cid, "to": c.get("to", "inbound"),
                      "status": c.get("status", "?"), "scenario": c.get("scenario", ""),
                      "started": c.get("started", 0),
                      "duration_s": c.get("duration_s"),
                      "turns": len(c.get("transcript") or [])})
    items.sort(key=lambda x: -(x["started"] or 0))
    return {"calls": items[:100]}

@app.get("/v1/calls/{call_id}")
async def call_status(call_id: str, tenant=Depends(verify_api_key)):
    call = CALLS.get(call_id) or _load_saved_calls().get(call_id)
    if not call:
        raise HTTPException(404, "Unknown call")
    return {k: v for k, v in call.items() if k not in ("agent_prompt",) and not k.startswith("_")} \
        | {"call_id": call_id}

@app.get("/v1/calls/{call_id}/transcript")
async def call_transcript(call_id: str, tenant=Depends(verify_api_key)):
    call = CALLS.get(call_id) or _load_saved_calls().get(call_id)
    if not call:
        raise HTTPException(404, "Unknown call")
    return {"call_id": call_id, "status": call.get("status"),
            "transcript": call.get("transcript") or []}

@app.post("/v1/calls/{call_id}/hangup")
async def hangup(call_id: str, tenant=Depends(verify_api_key)):
    call = CALLS.get(call_id)
    if not call:
        raise HTTPException(404, "Unknown call")
    async with httpx.AsyncClient(auth=ARI_AUTH) as c:
        await c.delete(f"{ARI_URL}/ari/channels/{call['channel_id']}")
    call["status"] = "ended"
    return {"ok": True}

# ---------------- ARI event loop + RTP<->WS audio bridge ----------------

class RTPBridge:
    """externalMedia RTP (slin16 @16k) <-> gateway websocket PCM frames.
    Also captures the conversation text (caller transcript + agent replies) into the call record."""
    def __init__(self, rtp_port: int, call: dict):
        self.rtp_port = rtp_port
        self.call = call
        self.remote = None
        self.seq = 0; self.ts = 0; self.ssrc = 0x56414920

    def _log_line(self, role: str, text: str):
        self.call.setdefault("transcript", []).append(
            {"role": role, "text": text,
             "t": round(time.time() - self.call.get("started", time.time()), 1)})

    async def run(self, stop: asyncio.Event):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.rtp_port)); sock.setblocking(False)
        loop = asyncio.get_event_loop()
        async with websockets.connect(GW_WS) as gw:
            # greet:true -> the agent SPEAKS FIRST when the callee answers (an outbound call
            # where the callee has to talk first feels broken).
            await gw.send(json.dumps({
                "event": "start",
                "system_prompt": self.call.get("agent_prompt", ""),
                "greet": True,
                "greeting_prompt": self.call.get("greeting_prompt")
                    or "Greet the person warmly in one short sentence, say you are an AI "
                       "assistant, and state why you are calling. Then ask your first question.",
            }))

            async def rtp_in():
                while not stop.is_set():
                    try:
                        data, addr = await asyncio.wait_for(
                            loop.sock_recvfrom(sock, 4096), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    self.remote = addr
                    pcm = data[12:]  # strip 12-byte RTP header (slin16 payload)
                    await gw.send(pcm)

            async def ws_out():
                async for msg in gw:
                    if stop.is_set():
                        break
                    if isinstance(msg, bytes):
                        # 24k TTS PCM -> 16k for slin16 call leg
                        pcm16k, _ = audioop.ratecv(msg, 2, 1, 24000, 16000, None)
                        # packetize 20ms (=640 bytes @16k mono PCM16)
                        for i in range(0, len(pcm16k), 640):
                            chunk = pcm16k[i:i+640]
                            hdr = struct.pack("!BBHII", 0x80, 118, self.seq & 0xFFFF,
                                              self.ts, self.ssrc)
                            self.seq += 1; self.ts += len(chunk)//2
                            if self.remote:
                                await loop.sock_sendto(sock, hdr + chunk, self.remote)
                            await asyncio.sleep(0.02)  # pace at real time
                    else:
                        # text events from the gateway = the conversation, fully transcribed
                        try:
                            d = json.loads(msg)
                        except Exception:
                            continue
                        if d.get("type") == "transcript" and d.get("text"):
                            self._log_line("caller", d["text"])
                        elif d.get("type") == "agent_text" and d.get("text"):
                            self._log_line("agent", d["text"])

            await asyncio.gather(rtp_in(), ws_out(), return_exceptions=True)
        sock.close()

async def ari_events():
    """Connect ARI WebSocket; handle StasisStart for inbound + originated calls."""
    import websockets as wsl
    user, pwd = ARI_AUTH
    url = ARI_URL.replace("http", "ws") + f"/ari/events?app=voiceai&api_key={user}:{pwd}"
    port_counter = [RTP_PORT_BASE]
    while True:
        try:
            async with wsl.connect(url) as ws:
                async for raw in ws:
                    ev = json.loads(raw)
                    if ev.get("type") == "StasisStart":
                        asyncio.create_task(handle_stasis(ev, port_counter))
                    elif ev.get("type") == "StasisEnd":
                        for cid, c in CALLS.items():
                            if c.get("channel_id") == ev["channel"]["id"]:
                                c["status"] = "ended"
                                c["duration_s"] = int(time.time() - c["started"])
                                stop_ev = c.get("_stop")
                                if stop_ev:
                                    stop_ev.set()          # tear down the RTP bridge promptly
                                _save_call(cid)            # persist status + full transcript
        except Exception as e:
            print(f"[ari] reconnect in 3s: {e}")
            await asyncio.sleep(3)

async def handle_stasis(ev, port_counter):
    ch = ev["channel"]; args = ev.get("args", [])
    call_id = args[0] if args else str(uuid.uuid4())
    call = CALLS.setdefault(call_id, {"status": "ringing", "channel_id": ch["id"],
                                      "agent_prompt": "", "started": time.time(),
                                      "tenant_id": "inbound"})
    call["status"] = "answered"
    port = port_counter[0]; port_counter[0] += 2
    async with httpx.AsyncClient(auth=ARI_AUTH, timeout=30) as c:
        await c.post(f"{ARI_URL}/ari/channels/{ch['id']}/answer")
        # create externalMedia channel -> RTP to us
        r = await c.post(f"{ARI_URL}/ari/channels/externalMedia", params={
            "app": "voiceai", "external_host": f"{EXTERNAL_MEDIA_HOST}:{port}",
            "format": "slin16"})
        em = r.json()
        # bridge caller + externalMedia
        br = (await c.post(f"{ARI_URL}/ari/bridges", params={"type": "mixing"})).json()
        await c.post(f"{ARI_URL}/ari/bridges/{br['id']}/addChannel",
                     params={"channel": f"{ch['id']},{em['id']}"})
    stop = asyncio.Event()
    call["_stop"] = stop

    async def _enforce_limit():
        """Cost control: hang up automatically when the call hits its duration limit."""
        limit = int(call.get("max_duration_s") or MAX_CALL_S)
        try:
            await asyncio.wait_for(stop.wait(), timeout=limit)
        except asyncio.TimeoutError:
            call["ended_reason"] = "time_limit"
            try:
                async with httpx.AsyncClient(auth=ARI_AUTH) as c:
                    await c.delete(f"{ARI_URL}/ari/channels/{ch['id']}")
            except Exception:
                pass
            stop.set()
    limiter = asyncio.create_task(_enforce_limit())

    bridge = RTPBridge(port, call)
    try:
        await bridge.run(stop)
    finally:
        stop.set(); limiter.cancel()
        call["status"] = "ended"
        call.setdefault("duration_s", int(time.time() - call["started"]))
        _save_call(call_id)

@app.on_event("startup")
async def startup():
    if os.getenv("DISABLE_ARI", "") != "1":
        asyncio.create_task(ari_events())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8004")))
