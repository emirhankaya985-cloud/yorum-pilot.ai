from pydantic import BaseModel, Field, field_validator

class Register(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=120)

    @field_validator('email')
    @classmethod
    def normalized_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count('@') != 1 or '.' not in email.split('@')[-1]:
            raise ValueError('Geçerli bir e-posta girin')
        return email

class Login(BaseModel):
    email: str
    password: str

class DraftUpdate(BaseModel):
    text: str = Field(min_length=2, max_length=4096)

    @field_validator('text')
    @classmethod
    def max_bytes(cls, value: str) -> str:
        if len(value.encode('utf-8')) > 4096:
            raise ValueError('Yanıt en fazla 4096 bayt olabilir')
        return value.strip()

class PublishRequest(BaseModel):
    idempotency_key: str = Field(min_length=12, max_length=64)
    confirm: bool
