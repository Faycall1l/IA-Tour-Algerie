from pydantic import BaseModel, Field


class OTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?[0-9]{7,15}$")


class OTPVerify(BaseModel):
    phone: str = Field(..., pattern=r"^\+?[0-9]{7,15}$")
    code: str = Field(..., min_length=4, max_length=8)


class TokenRefresh(BaseModel):
    refresh_token: str
