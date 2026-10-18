from pydantic import BaseModel, Field, field_validator


USERNAME_RE = r"^[A-Za-z0-9_]{3,32}$"


class RegisterRequest(BaseModel):
    # 账号规则：3–32 位字母/数字/下划线。不再强制邮箱格式。
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_RE,
                          description="登录账号，3-32 位字母、数字或下划线")
    password: str = Field(min_length=6, max_length=128,
                          description="密码，至少 6 位")
    # 邮箱改为可选，填了就校验格式，方便以后找回密码
    email: str | None = None

    @field_validator("username")
    @classmethod
    def _strip_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("账号不能为空")
        return v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("邮箱格式不正确，或留空不填")
        return v


class UserResponse(BaseModel):
    id: int
    username: str | None = None
    email: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
