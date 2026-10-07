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
    saga_id: int
    product_id: int
    quantity: int


class ReleaseRequest(BaseModel):
    saga_id: int

class ReservationResponse(BaseModel):
    id: int
    saga_id: int
    product_id: int
    quantity: int
    status: str

    class Config:
        from_attributes = True