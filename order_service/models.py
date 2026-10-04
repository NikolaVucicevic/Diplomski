from sqlalchemy import Column, Integer, Float, String
from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    saga_id = Column(Integer, unique=True, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="PENDING")