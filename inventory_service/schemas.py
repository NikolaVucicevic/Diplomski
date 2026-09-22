from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    quantity: int


class ProductResponse(BaseModel):
    id: int
    name: str
    quantity: int

    model_config = {
        "from_attributes": True
    }


class ReserveRequest(BaseModel):
    product_id: int
    quantity: int