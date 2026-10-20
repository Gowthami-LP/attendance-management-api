import hashlib
import json
from typing import Any
from uuid import uuid4


def create_fingerprint(payload: dict[str, Any]) -> str:
    """Generate a stable fingerprint for a request payload."""
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def claim_request(
    redis_client,
    key: str,
    fingerprint: str,
    ttl_seconds: int = 86400,
) -> dict[str, Any]:
    """Claim a request, identify a duplicate, or request a bounded retry."""
    for _ in range(3):
        owner_token = str(uuid4())
        claim = json.dumps(
            {
                "fingerprint": fingerprint,
                "owner_token": owner_token,
                "status": "processing",
            }
        )

        if await redis_client.set(key, claim, ex=ttl_seconds, nx=True):
            return {"status": "claimed", "owner_token": owner_token}

        existing_claim = await redis_client.get(key)
        if existing_claim is None:
            # The existing claim may have expired between SET NX and GET.
            continue

        existing = json.loads(existing_claim)
        if existing["fingerprint"] != fingerprint:
            return {"status": "conflict"}

        if existing.get("status", existing.get("state")) == "completed":
            return {
                "status": "completed",
                "response": existing["response"],
                "http_status": existing["http_status"],
            }
        return {"status": "processing"}

    return {"status": "retry"}


async def complete_request(
    redis_client,
    key: str,
    owner_token: str,
    fingerprint: str,
    response: dict[str, Any],
    http_status: int,
    ttl_seconds: int = 86400,
) -> bool:
    """Store the response if the caller still owns the claim."""
    completed_record = json.dumps(
        {
            "status": "completed",
            "fingerprint": fingerprint,
            "response": response,
            "http_status": http_status,
        }
    )
    script = """
    local current = redis.call('GET', KEYS[1])
    if not current then
        return 0
    end
    local record = cjson.decode(current)
    if record.owner_token ~= ARGV[1] then
        return 0
    end
    redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
    return 1
    """
    result = await redis_client.eval(
        script,
        1,
        key,
        owner_token,
        completed_record,
        ttl_seconds,
    )
    return bool(result)


async def release_request(
    redis_client,
    key: str,
    owner_token: str,
) -> bool:
    """Release the claim only if the caller still owns it."""
    script = """
    local current = redis.call('GET', KEYS[1])
    if not current then
        return 0
    end
    local record = cjson.decode(current)
    if record.owner_token ~= ARGV[1] then
        return 0
    end
    return redis.call('DEL', KEYS[1])
    """
    result = await redis_client.eval(script, 1, key, owner_token)
    return bool(result)
