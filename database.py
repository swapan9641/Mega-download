from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client['MegaBotDB']
users_col = db['users']

async def add_user(user_id, username):
    if not await users_col.find_one({"_id": user_id}):
        await users_col.insert_one({
            "_id": user_id, 
            "username": username, 
            "is_banned": False,
            "target_channel": None,
            "quality": "360p"
        })

async def get_all_users():
    return await users_col.find().to_list(length=None)

async def ban_user(user_id, state=True):
    await users_col.update_one({"_id": user_id}, {"$set": {"is_banned": state}})

async def is_banned(user_id):
    user = await users_col.find_one({"_id": user_id})
    return user.get("is_banned", False) if user else False

async def update_settings(user_id, key, value):
    await users_col.update_one({"_id": user_id}, {"$set": {key: value}})

async def get_user(user_id):
    return await users_col.find_one({"_id": user_id})
