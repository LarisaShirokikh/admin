from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    # URL, который используется для отображения (локальный после скачивания)
    url = Column(String, nullable=False)

    # Исходный URL с сайта-донора (сохраняем для истории)
    original_url = Column(String, nullable=True)

    # Флаг: скачана ли картинка локально
    is_local = Column(Boolean, default=False)

    # Основное изображение продукта
    is_main = Column(Boolean, default=False)

    # Размер файла в байтах (для статистики)
    file_size = Column(Integer, nullable=True)

    # Ошибка скачивания (если не удалось)
    download_error = Column(String, nullable=True)

    product = relationship("Product", back_populates="product_images")

    def __repr__(self):
        status = "local" if self.is_local else "external"
        return f"<ProductImage {self.id} [{status}] {self.url[:50]}>"