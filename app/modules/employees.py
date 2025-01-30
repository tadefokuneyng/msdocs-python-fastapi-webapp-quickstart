from fastapi import APIRouter, Form, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.models import Employee
from app.database import get_db

from app.models import Employee

# Create an APIRouter for employees
router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

# Employee list page
@router.get("/employees")
async def employee_page(request: Request, page: int = 1, page_size: int = 2, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse("/login")
    
    start = (page - 1) * page_size
    statement = select(Employee).order_by("name").limit(page_size).offset(start)
    employees = db.exec(statement).all()

    previous = page - 1 if page > 1 else None
    next = page + 1 if len(employees) == page_size else None

    return templates.TemplateResponse("employees/employees.html", {
        "request": request,
        "employees": employees,
        "previous": previous,
        "next": next
    })

# Delete employee
@router.post("/employees/{employee_id}/delete")
async def delete_employee(employee_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse("/login")
    
    employee = db.get(Employee, employee_id)
    db.delete(employee)
    db.commit()

    return RedirectResponse("/employees", status_code=302)

# Add employee form page
@router.get("/employees/add")
async def add_employee_form(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/login")
    
    return templates.TemplateResponse("employees/add_employee.html", {"request": request})

# Add employee form submission
@router.post("/employees/add")
async def add_employee(name: str = Form(...), position: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse("/login")

    new_employee = Employee(name=name, position=position)
    db.add(new_employee)
    db.commit()

    return RedirectResponse("/employees", status_code=302)

# Update employee form page
@router.get("/employees/{employee_id}/update")
async def update_employee_form(employee_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse("/login")

    employee = db.get(Employee, employee_id)

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return templates.TemplateResponse("employees/update_employee.html", {"request": request, "employee": employee})

# Update employee form submission
@router.post("/employees/{employee_id}/update")
async def update_employee(employee_id: int, name: str = Form(...), position: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse("/login")

    employee = db.get(Employee, employee_id)

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Update employee details
    employee.name = name
    employee.position = position

    db.add(employee)
    db.commit()
    return RedirectResponse("/employees", status_code=302)