from pydantic import BaseModel


class OrderCreate(BaseModel):
    product_id: int
    quantity: int
    price: float


class OrderResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: float
    status: str

    model_config = {
        "from_attributes": True
    }