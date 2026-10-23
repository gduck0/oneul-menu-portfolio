from pydantic import Field, SecretStr, field_validator

from app.food_contracts import StrictModel


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9가-힣_]+$')
    password: SecretStr = Field(min_length=10, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        return value.casefold()


class PublicUser(StrictModel):
    id: str
    username: str


class Identity(StrictModel):
    user: PublicUser | None
