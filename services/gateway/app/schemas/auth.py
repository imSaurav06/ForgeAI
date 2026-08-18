from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: str
    password: str = Field(...)

class TokenResponse(BaseModel):
    token: str
    user_id: str
    name: str
    email: str
    role: str
