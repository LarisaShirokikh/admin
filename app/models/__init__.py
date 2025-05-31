# app/models/__init__.py

from .banner import Banner
from .promotion import Promotion
from .import_log import ImportLog
from .brand import Brand
from .category import Category
from .catalog import Catalog
from .product import Product
from .product_image import ProductImage
from .video import Video
from .catalog_image import CatalogImage
from .review import Review
from .product_video import ProductVideo
from .product_ranking import ProductRanking

# Импорт связующих таблиц
from .attributes import product_categories

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
    "Review",  
    "product_categories",
    "ProductRanking",
    "ProductVideo"
]