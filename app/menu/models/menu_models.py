from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Allergen(BaseModel):
    id: str
    name: str
    nameIT: str
    icon: str
    descriptionIT: Optional[str] = None
    descriptionEN: Optional[str] = None


class ProductBase(BaseModel):
    name: str
    nameIT: str
    price: str
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: List[str] = []
    image: Optional[str] = None


class Product(ProductBase):
    id: int
    category_id: int
    subcategory_id: int


class ProductCreate(ProductBase):
    category_id: int
    subcategory_id: int


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: Optional[List[str]] = None
    image: Optional[str] = None


class SubcategoryBase(BaseModel):
    name: str
    nameIT: str
    image: Optional[str] = None


class Subcategory(SubcategoryBase):
    id: int
    category_id: int
    items: List[Product] = []


class SubcategoryCreate(SubcategoryBase):
    category_id: int


class SubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    image: Optional[str] = None


class CategoryBase(BaseModel):
    name: str
    nameIT: str
    image: Optional[str] = None


class Category(CategoryBase):
    id: int
    subcategories: List[Subcategory] = []


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    image: Optional[str] = None


class MenuResponse(BaseModel):
    categories: List[Category]
    allergens: List[Allergen]
