"""Conversation memory in Redis. Key = session_id. Stores system prompt + turn history."""
import json, os

class ConversationMemory:
    def __init__(self, redis_url: str | None = None):
        import redis.asyncio as redis
        self.r = redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        self.max_turns = int(os.getenv("MEMORY_MAX_TURNS", "40"))
        self.ttl = int(os.getenv("MEMORY_TTL_S", "7200"))

    async def init_session(self, session_id: str, system_prompt: str):
        await self.r.set(f"conv:{session_id}:system", system_prompt, ex=self.ttl)
        await self.r.delete(f"conv:{session_id}:turns")

    async def add_turn(self, session_id: str, role: str, content: str):
        key = f"conv:{session_id}:turns"
        await self.r.rpush(key, json.dumps({"role": role, "content": content}))
        await self.r.ltrim(key, -self.max_turns, -1)
        await self.r.expire(key, self.ttl)

    async def get_messages(self, session_id: str) -> list[dict]:
        system = await self.r.get(f"conv:{session_id}:system")
        turns = await self.r.lrange(f"conv:{session_id}:turns", 0, -1)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system.decode()})
        msgs += [json.loads(t) for t in turns]
        return msgs
