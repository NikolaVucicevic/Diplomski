from sqlalchemy import Column, Integer, String
from .database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)

class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)

    saga_id = Column(Integer, unique=True, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)

    status = Column(String, nullable=False, default="RESERVED")