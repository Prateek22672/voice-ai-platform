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
EXTERNAL_MEDIA_HOST = os.getenv("EXTERNAL_MEDIA_HOST", "telephony-service")
RTP_PORT_BASE = int(os.getenv("RTP_PORT_BASE", "18000"))

CALLS: dict[str, dict] = {}

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
    CALLS[call_id] = {"status": "dialing", "channel_id": ch["id"], "to": to,
                      "agent_prompt": body.get("agent_prompt", ""),
                      "tenant_id": tenant["tenant_id"], "started": time.time()}
    return {"call_id": call_id, "status": "dialing"}

@app.get("/v1/calls/{call_id}")
async def call_status(call_id: str, tenant=Depends(verify_api_key)):
    call = CALLS.get(call_id)
    if not call:
        raise HTTPException(404, "Unknown call")
    return {k: v for k, v in call.items() if k != "agent_prompt"} | {"call_id": call_id}

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
    """externalMedia RTP (slin16 @16k) <-> gateway websocket PCM frames."""
    def __init__(self, rtp_port: int, agent_prompt: str):
        self.rtp_port = rtp_port
        self.agent_prompt = agent_prompt
        self.remote = None
        self.seq = 0; self.ts = 0; self.ssrc = 0x56414920

    async def run(self, stop: asyncio.Event):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.rtp_port)); sock.setblocking(False)
        loop = asyncio.get_event_loop()
        async with websockets.connect(GW_WS) as gw:
            await gw.send(json.dumps({"event": "start", "system_prompt": self.agent_prompt}))

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
    bridge = RTPBridge(port, call.get("agent_prompt", ""))
    try:
        await bridge.run(stop)
    finally:
        call["status"] = "ended"

@app.on_event("startup")
async def startup():
    if os.getenv("DISABLE_ARI", "") != "1":
        asyncio.create_task(ari_events())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8004")))
