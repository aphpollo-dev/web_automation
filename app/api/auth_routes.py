from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.db.mongodb import get_database
import datetime
import os

# Constants for JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

auth_router = APIRouter(tags=["Authentication"])

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Utility functions for password hashing and JWT creation
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: datetime.timedelta | None = None):
    to_encode = data.copy()

    # Ensure that ACCESS_TOKEN_EXPIRE_MINUTES is an integer
    expire_minutes = int(ACCESS_TOKEN_EXPIRE_MINUTES)  # Convert to integer

    # Set the expiration time to 60 minutes (default) and include a timestamp
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expire_minutes)  # expiration

    # Convert datetime objects to ISO format strings
    to_encode.update({
        "exp": expire
    })

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        timestamp = payload.get("timestamp")  # Extract timestamp from the token

        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return {"username": username, "role": role, "timestamp": timestamp}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(required_role: str):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] != required_role:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user
    return role_checker

@auth_router.post("/login", response_model=Token)
async def login(user: UserLogin, db = Depends(get_database)):
    # Fetch user from MongoDB collection using the username
    user_data = await db.user.find_one({"username": user.username})  # Use await

    if not user_data:
        raise HTTPException(status_code=401, detail="User does not exist.")

    # Check if the password matches the hashed password
    if not verify_password(user.password, user_data["hashed_password"]):
        raise HTTPException(status_code=400, detail="Wrong password.")

    if not user_data.get("is_active", True):  # Ensure the account is active
        raise HTTPException(status_code=403, detail="User account is inactive")

    # Generate the JWT access token
    access_token = create_access_token(
        data={"sub": user_data["username"], "role": user_data.get("role", "admin")}
    )

    # Add the timestamp to the response
    return {"access_token": access_token, "token_type": "bearer",}

