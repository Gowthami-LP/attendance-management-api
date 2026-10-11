# Import HTTPException to return API errors
from fastapi import HTTPException, status

# Import ReturnDocument to return the updated MongoDB document
from pymongo import ReturnDocument

# Import DuplicateKeyError to handle MongoDB unique-index conflicts
from pymongo.errors import DuplicateKeyError

# Import the MongoDB employees collection
from app.database.mongodb import employees_collection

# Import the employee request and response schemas
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeUpdate


# Register a new employee in MongoDB
def create_employee(employee: EmployeeCreate) -> EmployeeResponse:
    # Convert validated employee details into a MongoDB document
    employee_document = {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "email": str(employee.email).lower(),
        "department": employee.department,
        "is_active": True,
    }

    try:
        # Insert the document into the employees collection
        employees_collection.insert_one(employee_document)

    except DuplicateKeyError as error:
        # Identify which unique field caused the conflict
        key_pattern = error.details.get("keyPattern", {})

        if "employee_id" in key_pattern:
            detail = "Employee ID already exists"
        elif "email" in key_pattern:
            detail = "Email address already exists"
        else:
            detail = "An employee record with duplicate data already exists"

        # Return HTTP 409 Conflict
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from error

    # Return the newly created employee without exposing MongoDB's internal _id
    return EmployeeResponse(**employee_document)


# Retrieve employees with optional query filters
def get_employees(
    department: str | None = None,
    is_active: bool | None = None,
) -> list[EmployeeResponse]:
    # Start with an empty MongoDB filter
    query: dict[str, object] = {}

    # Filter by department if supplied
    if department is not None:
        query["department"] = {
            "$regex": f"^{department}$",
            "$options": "i",
        }

    # Filter by active status if supplied
    if is_active is not None:
        query["is_active"] = is_active

    # Find matching records and exclude MongoDB's internal ID
    employee_documents = employees_collection.find(
        query,
        {"_id": 0},
    )

    # Convert MongoDB documents into validated response objects
    return [
        EmployeeResponse(**document)
        for document in employee_documents
    ]


# Retrieve one employee by ID
def get_employee_by_id(employee_id: str) -> EmployeeResponse:
    # Search MongoDB for the requested employee.
    employee = employees_collection.find_one(
        {"employee_id": employee_id},
        {"_id": 0},
    )

    # Return 404 if the employee does not exist.
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Convert the MongoDB document into the response schema.
    return EmployeeResponse(**employee)


# Update employee details
def update_employee(
    employee_id: str,
    employee_update: EmployeeUpdate,
) -> EmployeeResponse:
    # Include only fields explicitly supplied in the PATCH request.
    updates = employee_update.model_dump(exclude_unset=True)

    # Reject an empty update request.
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    # Do not allow null values for these required employee fields.
    if any(value is None for value in updates.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Updated fields cannot be null",
        )

    # Normalize email addresses before saving them.
    if "email" in updates:
        updates["email"] = str(updates["email"]).lower()

    try:
        # Update the matching employee and return the updated document.
        employee = employees_collection.find_one_and_update(
            {"employee_id": employee_id},
            {"$set": updates},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as error:
        # A different employee may already use this email address.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address already exists",
        ) from error

    # If MongoDB found no matching employee, return 404.
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Return the updated employee details.
    return EmployeeResponse(**employee)


# Deactivate an employee
def deactivate_employee(employee_id: str) -> EmployeeResponse:
    # Mark the employee inactive without deleting their record.
    employee = employees_collection.find_one_and_update(
        {"employee_id": employee_id},
        {"$set": {"is_active": False}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )

    # Return 404 if the employee does not exist.
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Return the employee with is_active set to False.
    return EmployeeResponse(**employee)
