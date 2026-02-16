import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()


client = MongoClient(os.getenv("MONGO_URI"))
db = client["telegram_inquiries"]
collection = db["messages"]
print(client.list_database_names())

