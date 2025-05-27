# app/models/__init__.py

"""
Импорт всех моделей для правильной работы SQLAlchemy и Alembic
"""

# Импорт моделей без внешних зависимостей

from .banner import Banner
from .promotion import Promotion
from .import_log import ImportLog

# Добавляем новые базовые модели
from .brand import Brand
from .color import Color

# Импорт моделей с внешними зависимостями
from .category import Category
from .catalog import Catalog
from .product import Product
from .product_image import ProductImage
from .video import Video
from .catalog_image import CatalogImage
from .review import Review
from .product_ranking import ProductRanking

# Импорт связующих таблиц
from .attributes import product_category, product_color

__all__ = [
    "Category",
    "Catalog",
    "Product",
    "ProductImage",
    "CatalogImage",
    "ImportLog",
    "Banner",
    "Promotion",
    "Video",
    "Brand",   
    "Color",
    "Review",  
    "product_category",
    "product_color",
    "ProductRanking"
]