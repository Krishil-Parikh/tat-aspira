"""MongoDB database layer with in-memory fallback for the TAT & Batch Monitoring System.

If MongoDB is not available at startup, automatically falls back to in-memory storage.
"""

import os
from datetime import datetime
from typing import List, Optional

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "tat_monitoring")

# Database state
client = None
db = None
USE_MEMORY = False

# In-memory fallback stores
_mem_samples: dict = {}       # sample_id -> doc
_mem_notifications: dict = {} # notification_id -> doc


async def connect_db():
    """Connect to MongoDB, fall back to in-memory if unavailable."""
    global client, db, USE_MEMORY

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=3000)
        # Ping to verify connection
        await client.admin.command("ping")
        db = client[DB_NAME]

        # Create indexes
        await db.samples.create_index("sample_id", unique=True)
        await db.samples.create_index("test_code")
        await db.samples.create_index("status")
        await db.samples.create_index("created_at")
        await db.notifications.create_index("sample_id")
        await db.notifications.create_index("created_at")

        USE_MEMORY = False
        print(f"✅ Connected to MongoDB: {MONGO_URL}/{DB_NAME}")

    except Exception as e:
        USE_MEMORY = True
        print(f"⚠️  MongoDB not available ({e.__class__.__name__}). Using IN-MEMORY storage.")
        print(f"   To use MongoDB, start it with: mongod")
        print(f"   The app will work fine without it — data won't persist across restarts.")


async def close_db():
    """Close MongoDB connection."""
    global client
    if client:
        client.close()
        print("🔌 MongoDB connection closed")


# =============================================================
# Sample operations
# =============================================================

async def insert_sample(sample_doc: dict) -> str:
    """Insert a new sample document."""
    if USE_MEMORY:
        _mem_samples[sample_doc["sample_id"]] = sample_doc.copy()
        return sample_doc["sample_id"]
    result = await db.samples.insert_one(sample_doc)
    return str(result.inserted_id)


async def get_sample(sample_id: str) -> Optional[dict]:
    """Get a sample by its sample_id."""
    if USE_MEMORY:
        return _mem_samples.get(sample_id)
    return await db.samples.find_one({"sample_id": sample_id})


async def get_all_samples(limit: int = 100) -> List[dict]:
    """Get all samples, most recent first."""
    if USE_MEMORY:
        items = sorted(_mem_samples.values(), key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return items[:limit]
    from pymongo import DESCENDING
    cursor = db.samples.find().sort("created_at", DESCENDING).limit(limit)
    return await cursor.to_list(length=limit)


async def update_sample(sample_id: str, update_data: dict) -> bool:
    """Update a sample document."""
    update_data["updated_at"] = datetime.now()
    if USE_MEMORY:
        if sample_id in _mem_samples:
            _mem_samples[sample_id].update(update_data)
            return True
        return False
    result = await db.samples.update_one(
        {"sample_id": sample_id},
        {"$set": update_data}
    )
    return result.modified_count > 0


async def delete_sample(sample_id: str) -> bool:
    """Delete a sample."""
    if USE_MEMORY:
        if sample_id in _mem_samples:
            del _mem_samples[sample_id]
            return True
        return False
    result = await db.samples.delete_one({"sample_id": sample_id})
    return result.deleted_count > 0


async def get_samples_by_status(status: str) -> List[dict]:
    """Get samples filtered by status."""
    if USE_MEMORY:
        items = [s for s in _mem_samples.values() if s.get("status") == status]
        return sorted(items, key=lambda x: x.get("created_at", datetime.min), reverse=True)
    from pymongo import DESCENDING
    cursor = db.samples.find({"status": status}).sort("created_at", DESCENDING)
    return await cursor.to_list(length=100)


# =============================================================
# Notification operations
# =============================================================

async def insert_notification(notif_doc: dict) -> str:
    """Insert a new notification."""
    if USE_MEMORY:
        _mem_notifications[notif_doc["notification_id"]] = notif_doc.copy()
        return notif_doc["notification_id"]
    result = await db.notifications.insert_one(notif_doc)
    return str(result.inserted_id)


async def get_notifications(limit: int = 50) -> List[dict]:
    """Get all notifications, most recent first."""
    if USE_MEMORY:
        items = sorted(_mem_notifications.values(), key=lambda x: x.get("created_at", datetime.min), reverse=True)
        return items[:limit]
    from pymongo import DESCENDING
    cursor = db.notifications.find().sort("created_at", DESCENDING).limit(limit)
    return await cursor.to_list(length=limit)


async def get_unread_notifications() -> List[dict]:
    """Get unread notifications."""
    if USE_MEMORY:
        items = [n for n in _mem_notifications.values() if not n.get("read", False)]
        return sorted(items, key=lambda x: x.get("created_at", datetime.min), reverse=True)
    from pymongo import DESCENDING
    cursor = db.notifications.find({"read": False}).sort("created_at", DESCENDING)
    return await cursor.to_list(length=50)


async def mark_notification_read(notification_id: str) -> bool:
    """Mark a notification as read."""
    if USE_MEMORY:
        if notification_id in _mem_notifications:
            _mem_notifications[notification_id]["read"] = True
            return True
        return False
    result = await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"read": True}}
    )
    return result.modified_count > 0


async def get_sample_count() -> int:
    """Get total sample count."""
    if USE_MEMORY:
        return len(_mem_samples)
    return await db.samples.count_documents({})


async def get_notification_count() -> int:
    """Get unread notification count."""
    if USE_MEMORY:
        return sum(1 for n in _mem_notifications.values() if not n.get("read", False))
    return await db.notifications.count_documents({"read": False})


async def clear_all_data():
    """Clear all samples and notifications."""
    if USE_MEMORY:
        _mem_samples.clear()
        _mem_notifications.clear()
        return
    await db.samples.delete_many({})
    await db.notifications.delete_many({})
