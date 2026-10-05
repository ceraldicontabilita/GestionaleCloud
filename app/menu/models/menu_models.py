from pydantic import BaseModel, StrictBool
from typing import List, Optional


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
    # False = nascosto dal menu pubblico (resta visibile nell'area admin).
    visible: bool = True
    # Prezzo AL BANCO (``price`` e' quello al tavolo). Vuoto = non deciso, mai un valore di ripiego.
    prezzo_banco: Optional[float] = None


class Product(ProductBase):
    id: int
    category_id: int
    subcategory_id: int


class ProductCreate(ProductBase):
    category_id: int
    subcategory_id: int


class ProductVisibility(BaseModel):
    visible: StrictBool


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: Optional[List[str]] = None
    image: Optional[str] = None
    visible: Optional[bool] = None
    # > 0 = prezzo al banco; 0 = togli il prezzo al banco
    prezzo_banco: Optional[float] = None


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
