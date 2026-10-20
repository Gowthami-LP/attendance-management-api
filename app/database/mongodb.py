# Import os to read environment variables
import os

# Import load_dotenv to load values from the project's .env file
from dotenv import load_dotenv

# Import MongoClient to connect to MongoDB
from pymongo import MongoClient
from pymongo.collection import Collection

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

# Tenant registry.
tenants_collection = database["tenants"]

# User-to-tenant membership records.
tenant_memberships_collection = database["tenant_memberships"]

# Select the employees collection
employees_collection = database["employees"]

# Collection for administrator accounts.
admins_collection = database["admins"]

# MongoDB collection that stores attendance records.
attendance_collection = database["attendance"]

# MongoDB collection for email notification history.
notifications_collection = database["notifications"]

# MongoDB collection that tracks queued employee import jobs.
employee_import_jobs_collection = database["employee_import_jobs"]


def _drop_legacy_indexes(
    collection: Collection,
    index_names: tuple[str, ...],
) -> None:
    existing_indexes = collection.index_information()
    for index_name in index_names:
        if index_name in existing_indexes:
            collection.drop_index(index_name)


def create_tenant_indexes() -> None:
    # One tenant per normalized slug.
    tenants_collection.create_index(
        [("slug", 1)],
        unique=True,
    )

    # Unique tenant ID lookup.
    tenants_collection.create_index(
        [("id", 1)],
        unique=True,
    )

    # A user's membership is unique within a tenant.
    tenant_memberships_collection.create_index(
        [("tenant_id", 1), ("user_id", 1)],
        unique=True,
    )


# Create indexes when the application starts
def create_database_indexes() -> None:
    # Global unique indexes prevent the same identifier being used in separate tenants.
    _drop_legacy_indexes(employees_collection, ("employee_id_1", "email_1"))

    # An employee ID is unique within a tenant.
    employees_collection.create_index(
        [("tenant_id", 1), ("employee_id", 1)],
        unique=True,
    )

    # Email addresses must also be unique within a tenant.
    employees_collection.create_index(
        [("tenant_id", 1), ("email", 1)],
        unique=True,
    )


def create_admin_indexes() -> None:
    # Ensure each admin email is unique.
    admins_collection.create_index(
        "email",
        unique=True,
    )


def create_attendance_indexes() -> None:
    # The old unique index did not include the tenant identifier.
    _drop_legacy_indexes(attendance_collection, ("employee_id_1_date_1",))

    # Permit only one attendance session per employee per local date within a tenant.
    attendance_collection.create_index(
        [("tenant_id", 1), ("employee_id", 1), ("date", 1)],
        unique=True,
    )

    # Efficient tenant-scoped attendance lookups.
    attendance_collection.create_index(
        [("tenant_id", 1), ("employee_id", 1), ("date", -1)],
    )

    # Keep check-in retries associated with their original attendance record.
    attendance_collection.create_index(
        [("tenant_id", 1), ("check_in_idempotency_key_hash", 1)],
        unique=True,
        partialFilterExpression={"check_in_idempotency_key_hash": {"$type": "string"}},
    )

    # Keep check-out retries associated with the attendance record they updated.
    attendance_collection.create_index(
        [("tenant_id", 1), ("check_out_idempotency_key_hash", 1)],
        unique=True,
        partialFilterExpression={"check_out_idempotency_key_hash": {"$type": "string"}},
    )

    # Speed up report queries that filter attendance by date within a tenant.
    attendance_collection.create_index(
        [("tenant_id", 1), ("date", 1)],
    )


def create_notification_indexes() -> None:
    # The old unique index did not include the tenant identifier.
    _drop_legacy_indexes(
        notifications_collection,
        ("employee_id_1_week_start_1",),
    )

    # Ensure each notification has a unique notification_id for fast lookup.
    notifications_collection.create_index(
        "notification_id",
        unique=True,
    )

    # Prevent more than one notification record per employee per week within a tenant.
    notifications_collection.create_index(
        [("tenant_id", 1), ("employee_id", 1), ("week_start", 1)],
        unique=True,
    )

    # Speed up queries for notifications by delivery status within a tenant.
    notifications_collection.create_index(
        [("tenant_id", 1), ("status", 1)],
    )

    # Speed up queries for notifications across workers.
    notifications_collection.create_index("status")
