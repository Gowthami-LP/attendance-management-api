# Import os to read environment variables
import os

# Import load_dotenv to load values from the project's .env file
from dotenv import load_dotenv

# Import MongoClient to connect to MongoDB
from pymongo import MongoClient

# Load variables from the project root's .env file
load_dotenv()

# Read the MongoDB connection URL
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Read the database name
MONGO_DATABASE = os.getenv(
    "MONGO_DATABASE",
    "attendance_management_db",
)

# Create a MongoDB client
# The timeout prevents connection attempts from hanging for too long
client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
)

# Select the application database
database = client[MONGO_DATABASE]

# Select the employees collection
employees_collection = database["employees"]

# Collection for administrator accounts.
admins_collection = database["admins"]

# MongoDB collection that stores attendance records.
attendance_collection = database["attendance"]

# MongoDB collection for email notification history.
notifications_collection = database["notifications"]


# Create indexes when the application starts
def create_database_indexes() -> None:
    # Employee IDs must be unique
    employees_collection.create_index(
        "employee_id",
        unique=True,
    )

    # Email addresses must also be unique
    employees_collection.create_index(
        "email",
        unique=True,
    )


def create_admin_indexes() -> None:
    # Ensure each admin email is unique.
    admins_collection.create_index(
        "email",
        unique=True,
    )


def create_attendance_indexes() -> None:
    # Permit only one attendance session per employee per local date.
    attendance_collection.create_index(
        [("employee_id", 1), ("date", 1)],
        unique=True,
    )

    # Speed up report queries that filter attendance by date.
    attendance_collection.create_index("date")


def create_notification_indexes() -> None:
    # Ensure each notification has a unique notification_id for fast lookup.
    notifications_collection.create_index(
        "notification_id",
        unique=True,
    )

    # Prevent more than one notification record per employee per week.
    notifications_collection.create_index(
        [("employee_id", 1), ("week_start", 1)],
        unique=True,
    )

    # Speed up queries for notifications by delivery status.
    notifications_collection.create_index("status")
