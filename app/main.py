# Import asynccontextmanager to manage application startup and shutdown
import logging
from contextlib import asynccontextmanager

# Import FastAPI
from fastapi import FastAPI, Response, status
from pymongo.errors import PyMongoError

# Import the MongoDB client and index setup functions
from app.database.mongodb import (
    client,
    create_admin_indexes,
    create_attendance_indexes,
    create_database_indexes,
    create_notification_indexes,
    create_tenant_indexes,
)
from app.database.redis_client import check_redis_connection, close_redis_connection
from app.middleware.logging_middleware import StructuredLoggingMiddleware

# Import the application routers
from app.routers.attendance import router as attendance_router
from app.routers.auth import router as auth_router
from app.routers.compliance import router as compliance_router
from app.routers.employees import router as employee_router
from app.routers.health import router as health_router
from app.routers.notifications import router as notifications_router
from app.routers.reports import router as reports_router
from app.routers.tenants import router as tenants_router
from app.services.scheduler_service import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


# Define startup and shutdown operations
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Verify that MongoDB is reachable
        client.admin.command("ping")

        # Create unique indexes for employee records
        create_database_indexes()

        # Create tenant and membership indexes
        create_tenant_indexes()

        # Create the admin account index
        create_admin_indexes()

        # Create the attendance indexes
        create_attendance_indexes()

        # Create notification indexes
        create_notification_indexes()

        # Start the weekly notification scheduler
        start_scheduler()

        # Redis is an optional cache; keep the API available if it is down.
        try:
            app.state.redis_available = await check_redis_connection()
        except Exception:
            app.state.redis_available = False
            logger.warning(
                "Redis is unavailable; continuing without cache", exc_info=True
            )

        # Allow FastAPI to serve requests
        yield
    finally:
        # Stop the scheduler during application shutdown
        stop_scheduler()

        # Close the MongoDB connection when the application shuts down
        client.close()

        # Release the asynchronous Redis client during application shutdown.
        await close_redis_connection()


# Create the FastAPI application instance
app = FastAPI(
    title="Central Attendance Management System",
    description="Backend APIs for employee attendance and policy compliance.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register structured logging and request ID middleware
app.add_middleware(StructuredLoggingMiddleware)

# Register admin authentication endpoints
app.include_router(auth_router)

# Register employee endpoints
app.include_router(employee_router)

# Register attendance endpoints
app.include_router(attendance_router)

# Register attendance reporting endpoints
app.include_router(reports_router)

# Register weekly attendance compliance endpoint
app.include_router(compliance_router)

# Register notification endpoints
app.include_router(notifications_router)

# Register tenant registry endpoints
app.include_router(tenants_router)

# Register dependency health endpoints
app.include_router(health_router)


# Define the root endpoint
@app.get("/")
def home():
    # Return a welcome message when someone accesses the root URL
    return {
        "message": "Welcome to the Attendance Management System API",
        "status": "running",
    }


# Define a health-check endpoint
@app.get("/health")
def health_check():
    # Return a simple response to confirm the application is responding
    return {
        "status": "healthy",
        "application": "attendance-management-api",
    }


# Liveness check: confirms the application process is running and responding
@app.get("/health/live")
def liveness_check():
    return {
        "status": "alive",
        "application": "attendance-management-api",
    }


# Readiness check: confirms external dependencies (MongoDB) are available
@app.get("/health/ready")
def readiness_check(response: Response):
    try:
        client.admin.command("ping")
        return {
            "status": "ready",
            "database": "connected",
            "application": "attendance-management-api",
        }
    except (PyMongoError, OSError, RuntimeError) as error:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "disconnected",
            "error": str(error),
            "application": "attendance-management-api",
        }
