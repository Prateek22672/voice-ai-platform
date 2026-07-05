"""NATS helper. Services publish/subscribe events through this."""
import json, os
import nats

_nc = None

async def get_nats():
    global _nc
    if _nc is None or _nc.is_closed:
        _nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    return _nc

async def publish(subject: str, payload: dict):
    nc = await get_nats()
    await nc.publish(subject, json.dumps(payload).encode())

async def subscribe(subject: str, cb):
    nc = await get_nats()
    async def handler(msg):
        await cb(json.loads(msg.data.decode()))
    await nc.subscribe(subject, cb=handler)
