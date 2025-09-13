"""
Redis-based session management for chat and conflict resolution
"""
import redis
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import uuid
from app.config import settings


class SessionManager:
    """Manages user sessions and temporary data in Redis"""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis connection"""
        redis_url = redis_url or getattr(settings, 'redis_url', 'redis://localhost:6379/0')

        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            self.enabled = True
            print("Redis connection established")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            print(f"Redis connection failed: {e}. Using in-memory fallback.")
            self.redis_client = None
            self.enabled = False
            self.memory_store = {}

    def create_session(self, user_id: Optional[str] = None,
                      ttl_hours: int = 24) -> str:
        """Create a new session"""
        session_id = str(uuid.uuid4())
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "context": {}
        }

        self.set_session(session_id, session_data, ttl_hours)
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        if self.enabled:
            try:
                data = self.redis_client.get(f"session:{session_id}")
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"Redis get error: {e}")
        else:
            # Fallback to memory store
            return self.memory_store.get(f"session:{session_id}")

        return None

    def set_session(self, session_id: str, data: Dict[str, Any],
                   ttl_hours: int = 24):
        """Set or update session data"""
        if self.enabled:
            try:
                self.redis_client.setex(
                    f"session:{session_id}",
                    timedelta(hours=ttl_hours),
                    json.dumps(data, default=str)
                )
            except Exception as e:
                print(f"Redis set error: {e}")
                # Fallback to memory
                self.memory_store[f"session:{session_id}"] = data
        else:
            self.memory_store[f"session:{session_id}"] = data

    def add_message(self, session_id: str, role: str, content: str,
                   metadata: Optional[Dict] = None):
        """Add a message to session history"""
        session = self.get_session(session_id)
        if not session:
            session = {
                "session_id": session_id,
                "messages": [],
                "context": {}
            }

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        session["messages"].append(message)

        # Keep only last 100 messages
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-100:]

        self.set_session(session_id, session)

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get session messages"""
        session = self.get_session(session_id)
        if session:
            messages = session.get("messages", [])
            return messages[-limit:] if limit else messages
        return []

    def set_context(self, session_id: str, key: str, value: Any):
        """Set context value for session"""
        session = self.get_session(session_id)
        if not session:
            session = {"session_id": session_id, "messages": [], "context": {}}

        session["context"][key] = value
        self.set_session(session_id, session)

    def get_context(self, session_id: str, key: Optional[str] = None) -> Any:
        """Get context value(s) from session"""
        session = self.get_session(session_id)
        if session:
            context = session.get("context", {})
            if key:
                return context.get(key)
            return context
        return None if key else {}

    # Conflict resolution specific methods
    def store_conflict(self, conflict_id: str, conflict_data: Dict[str, Any],
                      ttl_hours: int = 72):
        """Store a conflict for human review"""
        key = f"conflict:{conflict_id}"

        conflict_data["conflict_id"] = conflict_id
        conflict_data["created_at"] = datetime.now().isoformat()
        conflict_data["status"] = "pending"

        if self.enabled:
            try:
                self.redis_client.setex(
                    key,
                    timedelta(hours=ttl_hours),
                    json.dumps(conflict_data, default=str)
                )
                # Add to conflict queue
                self.redis_client.lpush("conflict_queue", conflict_id)
            except Exception as e:
                print(f"Redis conflict store error: {e}")
                self.memory_store[key] = conflict_data
        else:
            self.memory_store[key] = conflict_data

    def get_conflict(self, conflict_id: str) -> Optional[Dict[str, Any]]:
        """Get conflict data"""
        key = f"conflict:{conflict_id}"

        if self.enabled:
            try:
                data = self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"Redis get conflict error: {e}")
        else:
            return self.memory_store.get(key)

        return None

    def resolve_conflict(self, conflict_id: str, resolution: Dict[str, Any]):
        """Mark conflict as resolved"""
        conflict = self.get_conflict(conflict_id)
        if conflict:
            conflict["status"] = "resolved"
            conflict["resolution"] = resolution
            conflict["resolved_at"] = datetime.now().isoformat()

            if self.enabled:
                try:
                    self.redis_client.setex(
                        f"conflict:{conflict_id}",
                        timedelta(hours=24),  # Keep resolved conflicts for 24h
                        json.dumps(conflict, default=str)
                    )
                except Exception as e:
                    print(f"Redis resolve conflict error: {e}")
            else:
                self.memory_store[f"conflict:{conflict_id}"] = conflict

    def get_pending_conflicts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending conflicts for review"""
        conflicts = []

        if self.enabled:
            try:
                # Get conflict IDs from queue
                conflict_ids = self.redis_client.lrange("conflict_queue", 0, limit - 1)
                for conflict_id in conflict_ids:
                    conflict = self.get_conflict(conflict_id)
                    if conflict and conflict.get("status") == "pending":
                        conflicts.append(conflict)
            except Exception as e:
                print(f"Redis get pending conflicts error: {e}")
        else:
            # Fallback to memory store
            for key, value in self.memory_store.items():
                if key.startswith("conflict:") and value.get("status") == "pending":
                    conflicts.append(value)
                    if len(conflicts) >= limit:
                        break

        return conflicts

    # Cache management
    def cache_set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Set cache value"""
        cache_key = f"cache:{key}"

        if self.enabled:
            try:
                self.redis_client.setex(
                    cache_key,
                    timedelta(seconds=ttl_seconds),
                    json.dumps(value, default=str)
                )
            except Exception as e:
                print(f"Redis cache set error: {e}")
        else:
            self.memory_store[cache_key] = value

    def cache_get(self, key: str) -> Optional[Any]:
        """Get cache value"""
        cache_key = f"cache:{key}"

        if self.enabled:
            try:
                data = self.redis_client.get(cache_key)
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"Redis cache get error: {e}")
        else:
            return self.memory_store.get(cache_key)

        return None

    def cache_delete(self, key: str):
        """Delete cache value"""
        cache_key = f"cache:{key}"

        if self.enabled:
            try:
                self.redis_client.delete(cache_key)
            except Exception as e:
                print(f"Redis cache delete error: {e}")
        else:
            self.memory_store.pop(cache_key, None)


# Singleton instance
session_manager = SessionManager()