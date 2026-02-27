from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.products import router as products_router
from app.api.v1.posts import router as posts_router
from app.api.v1.search import router as search_router
# from app.api.v1.sitemap import router as sitemap_router
from app.api.v1.analytics import router as analytics_router

from app.api.v1.productsmgmt import router as productsmgmt_router
from app.api.v1.categoriesmgmt import router as categoriesmgmt_router
from app.api.v1.catalogsmgmt import router as catalogsmgmt_router
from app.api.v1.brandsmgmt import router as brandsmgmt_router
from app.api.v1.importlogsmgmt import router as importlogsmgmt_router
from app.api.v1.scrapermgmt import router as scrapermgmt_router
from app.api.v1.videomgmt import router as videomgmt_router
from app.api.v1.analyticsmgmt import router as analyticsmgmt_router
from app.api.v1.brands import router as brands_router
from app.api.v1.videos import router as videos_router
from app.api.v1.catalogs import router as catalogs_router
from app.api.v1.categories import router as categories_router

api_router = APIRouter(prefix="/api/v1")

# Auth
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])

# Public
api_router.include_router(products_router, prefix="/products", tags=["Products"])
api_router.include_router(posts_router, prefix="/posts", tags=["Posts"])
api_router.include_router(search_router, prefix="/search", tags=["Search"])
# api_router.include_router(sitemap_router, prefix="/sitemap", tags=["Sitemap"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])

# Admin
api_router.include_router(productsmgmt_router, prefix="/productsmgmt", tags=["Products Admin"])
api_router.include_router(categoriesmgmt_router, prefix="/categoriesmgmt", tags=["Categories Admin"])
api_router.include_router(catalogsmgmt_router, prefix="/catalogsmgmt", tags=["Catalogs Admin"])
api_router.include_router(brandsmgmt_router, prefix="/brandsmgmt", tags=["Brands Admin"])
api_router.include_router(importlogsmgmt_router, prefix="/importlogsmgmt", tags=["Import Logs Admin"])
api_router.include_router(scrapermgmt_router, prefix="/scrapermgmt", tags=["Scraper Admin"])
api_router.include_router(videomgmt_router, prefix="/videomgmt", tags=["Video Admin"])
api_router.include_router(analyticsmgmt_router, prefix="/analyticsmgmt", tags=["Analytics Admin"])
api_router.include_router(brands_router, prefix="/brands", tags=["Brands"])
api_router.include_router(videos_router, prefix="/videos", tags=["Videos"])
api_router.include_router(catalogs_router, prefix="/catalogs", tags=["Catalogs"])
api_router.include_router(categories_router, prefix="/categories", tags=["Categories"])
