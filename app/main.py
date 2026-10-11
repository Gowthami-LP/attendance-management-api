# Import asynccontextmanager to manage application startup and shutdown
from contextlib import asynccontextmanager

# Import FastAPI
from fastapi import FastAPI

# Import the MongoDB client and index setup functions
from app.database.mongodb import (
    client,
    create_admin_indexes,
    create_attendance_indexes,
    create_database_indexes,
    create_notification_indexes,
)

# Import the application routers
from app.routers.attendance import router as attendance_router
from app.routers.auth import router as auth_router
from app.routers.compliance import router as compliance_router
from app.routers.employees import router as employee_router
from app.routers.notifications import router as notifications_router
from app.routers.reports import router as reports_router
from app.services.scheduler_service import start_scheduler, stop_scheduler


# Define startup and shutdown operations
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Verify that MongoDB is reachable
        client.admin.command("ping")

        # Create unique indexes for employee records
        create_database_indexes()

        # Create the admin account index
        create_admin_indexes()

        # Create the attendance indexes
        create_attendance_indexes()

        # Create notification indexes
        create_notification_indexes()

        # Start the weekly notification scheduler
        start_scheduler()

        # Allow FastAPI to serve requests
        yield
    finally:
        # Stop the scheduler during application shutdown
        stop_scheduler()

        # Close the MongoDB connection when the application shuts down
        client.close()

# Create the FastAPI application instance
app = FastAPI(
    title="Central Attendance Management System",
    description="Backend APIs for employee attendance and policy compliance.",
    version="1.0.0",
    lifespan=lifespan,
)

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
