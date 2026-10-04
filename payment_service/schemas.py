from pydantic import BaseModel


class AccountCreate(BaseModel):
    client_id: int
    balance: float


class AccountResponse(BaseModel):
    id: int
    client_id: int
    balance: float

    model_config = {
        "from_attributes": True
    }


class PaymentCreate(BaseModel):
    saga_id: int
    order_id: int
    account_id: int
    amount: float


class PaymentResponse(BaseModel):
    id: int
    saga_id: int
    order_id: int
    account_id: int
    amount: float
    status: str

    model_config = {
        "from_attributes": True
    }


class PaymentRefund(BaseModel):
    saga_id: int