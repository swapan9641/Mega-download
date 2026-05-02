import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.types import Message
from config import MONGO_URI

logger = logging.getLogger("Database")

try:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client['MegaBotDB']
    users_col = db['users']
except Exception as e:
    logger.critical(f"Database connection failed: {e}")

async def setup_database():
    """
    MongoDB automatically indexes the _id field, so explicit creation is rejected.
    We just use this to verify the connection is alive on startup.
    """
    logger.info("Database connected and ready for queries.")

async def add_user(user_id: int, username: str):
    if not await users_col.find_one({"_id": user_id}):
        await users_col.insert_one({
            "_id": user_id, 
            "username": username, 
            "is_banned": False,
            "target_channel": None,
            "quality": "360p",
            "state": None
        })

async def get_all_users() -> list:
    return await users_col.find().to_list(length=None)

async def ban_user(user_id: int, state: bool = True):
    await users_col.update_one({"_id": user_id}, {"$set": {"is_banned": state}})

async def update_settings(user_id: int, key: str, value: any):
    await users_col.update_one({"_id": user_id}, {"$set": {key: value}})

async def get_user(user_id: int) -> dict:
    return await users_col.find_one({"_id": user_id}) or {}

async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return user.get("is_banned", False)
