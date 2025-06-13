# app/models/posts.py

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# Таблица связи many-to-many для постов и тегов
post_tags_association = Table(
    'posts_tags',
    Base.metadata,
    Column('post_id', Integer, ForeignKey('posts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('post_tags.id'), primary_key=True)
)


class PostAuthor(Base):
    """Модель автора поста"""
    __tablename__ = "post_authors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    avatar = Column(String(500))  # URL к аватарке
    role = Column(String(100))  # Должность автора
    bio = Column(Text)  # Биография
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    posts = relationship("Post", back_populates="author")


class PostTag(Base):
    """Модель тега поста"""
    __tablename__ = "post_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    description = Column(Text)
    color = Column(String(7))  # HEX цвет тега #FFFFFF
    posts_count = Column(Integer, default=0)  # Количество постов с этим тегом
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    posts = relationship("Post", secondary=post_tags_association, back_populates="tags")


class PostMedia(Base):
    """Модель медиа-файлов поста"""
    __tablename__ = "post_media"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    type = Column(String(20), nullable=False)  # image, video
    url = Column(String(500), nullable=False)  # URL к файлу
    thumbnail = Column(String(500))  # URL к превью (для видео)
    alt_text = Column(String(255))  # Альтернативный текст
    caption = Column(Text)  # Подпись к медиа
    order = Column(Integer, default=0)  # Порядок отображения
    is_featured = Column(Boolean, default=False, index=True)  # Главное медиа поста
    file_size = Column(Integer)  # Размер файла в байтах
    width = Column(Integer)  # Ширина изображения/видео
    height = Column(Integer)  # Высота изображения/видео
    duration = Column(Integer)  # Длительность видео в секундах
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    post = relationship("Post", back_populates="media")


class Post(Base):
    """Модель поста/новости"""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(550), nullable=False, unique=True, index=True)
    excerpt = Column(Text)  # Краткое описание
    content = Column(Text, nullable=False)  # Основной контент в HTML
    
    # SEO поля
    meta_title = Column(String(500))
    meta_description = Column(Text)
    meta_keywords = Column(String(500))
    
    # Статусы и флаги
    status = Column(String(20), default="draft")  # draft, published, archived
    is_published = Column(Boolean, default=False, index=True)
    is_featured = Column(Boolean, default=False, index=True)  # Рекомендуемый пост
    is_pinned = Column(Boolean, default=False, index=True)    # Закрепленный пост
    
    # Связи
    author_id = Column(Integer, ForeignKey("post_authors.id"))
    # featured_media_id убрали - будем получать через PostMedia.is_featured=True
    
    # Статистика
    views_count = Column(Integer, default=0, index=True)
    likes_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    
    # Даты
    published_at = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Дополнительные данные в JSON
    extra_data = Column(JSON)

    # Связи
    author = relationship("PostAuthor", back_populates="posts")
    tags = relationship("PostTag", secondary=post_tags_association, back_populates="posts")
    media = relationship("PostMedia", back_populates="post", order_by="PostMedia.order")
    
    # Свойство для получения главного медиа
    @property
    def featured_media(self):
        """Получить главное медиа поста"""
        for media_item in self.media:
            if media_item.is_featured:
                return media_item
        # Если нет featured, возвращаем первое по порядку
        return self.media[0] if self.media else None


class PostView(Base):
    """Модель для отслеживания просмотров постов"""
    __tablename__ = "post_views"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    ip_address = Column(String(45))  # IPv4/IPv6
    user_agent = Column(Text)
    referer = Column(String(500))
    session_id = Column(String(100))
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Связи
    post = relationship("Post")


class PostLike(Base):
    """Модель лайков постов"""
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    ip_address = Column(String(45))  # Для анонимных лайков
    session_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    post = relationship("Post")