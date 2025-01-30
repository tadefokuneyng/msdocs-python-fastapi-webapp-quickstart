from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.models import User
from app.database import get_db
from passlib.context import CryptContext

# Password hashing configuration
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Create an APIRouter for users
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Login form
@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("users/login.html", {"request": request})

# Login form submission and session management
@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    statement = select(User).where(User.username == username)
    user = db.exec(statement).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse("users/login.html", {"request": request, "error": "Invalid credentials"})
    
    # Store the logged-in user in the session
    request.session["user"] = username
    return RedirectResponse("/employees", status_code=302)

# Route to render the Add User form
@router.get("/users/add")
async def add_user_form(request: Request):
    return templates.TemplateResponse("users/add_user.html", {"request": request})

# Add a new user
@router.post("/users/add")
async def add_user(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    hashed_password = pwd_context.hash(password)
    new_user = User(username=username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    
    return RedirectResponse("/users/add", status_code=302)
