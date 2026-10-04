from sqlalchemy import Column, Integer, Float, String
from .database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False)
    balance = Column(Float, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    saga_id = Column(Integer, unique=True, nullable=False)
    order_id = Column(Integer, nullable=False)
    account_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default="COMPLETED")