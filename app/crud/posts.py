# app/crud/posts.py

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, desc, asc, func, text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError

from app.models.posts import Post, PostAuthor, PostTag, PostMedia, PostView, PostLike, post_tags_association
from app.schemas.posts import (
    PostCreate, PostUpdate, PostSearchParams,
    PostAuthorCreate, PostAuthorUpdate,
    PostTagCreate, PostTagUpdate,
    PostMediaCreate, PostMediaUpdate,
    PostViewCreate, PostLikeCreate
)


class PostsCRUD:
    """CRUD операции для постов"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # === POSTS ===

    def _get_featured_media(self, post: Post) -> Optional[PostMedia]:
        """Получить главное медиа поста"""
        if not post.media:
            return None
        
        # Ищем медиа с флагом is_featured
        for media_item in post.media:
            if media_item.is_featured:
                return media_item
        
        # Если нет featured, возвращаем первое по порядку
        return post.media[0] if post.media else None

    async def get_post(self, post_id: int) -> Optional[Post]:
        """Получить пост по ID"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(Post.id == post_id)
        )
        
        result = await self.db.execute(stmt)
        post = result.scalar()
        
        if post:
            # Добавляем featured_media как свойство
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return post

    async def get_post_by_slug(self, slug: str) -> Optional[Post]:
        """Получить пост по slug"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(Post.slug == slug)
        )
        
        result = await self.db.execute(stmt)
        post = result.scalar()
        
        if post:
            # Добавляем featured_media как свойство
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return post

    async def get_posts(
        self,
        skip: int = 0,
        limit: int = 20,
        search_params: Optional[PostSearchParams] = None
    ) -> tuple[List[Post], int]:
        """Получить список постов с фильтрацией и пагинацией"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
        )

        # Применяем фильтры
        if search_params:
            stmt = self._apply_search_filters(stmt, search_params)

        # Общее количество
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()

        # Сортировка
        if search_params and search_params.order_by:
            order_field = getattr(Post, search_params.order_by, Post.created_at)
            if search_params.order_dir == "asc":
                stmt = stmt.order_by(asc(order_field))
            else:
                stmt = stmt.order_by(desc(order_field))
        else:
            stmt = stmt.order_by(desc(Post.created_at))

        # Пагинация
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        # Добавляем featured_media для каждого поста
        for post in posts:
            setattr(post, 'featured_media', self._get_featured_media(post))

        return posts, total

    def _apply_search_filters(self, stmt, search_params: PostSearchParams):
        """Применить фильтры поиска к запросу"""
        if search_params.q:
            search_term = f"%{search_params.q}%"
            stmt = stmt.filter(
                or_(
                    Post.title.ilike(search_term),
                    Post.excerpt.ilike(search_term),
                    Post.content.ilike(search_term)
                )
            )

        if search_params.tag_id:
            stmt = stmt.join(Post.tags).filter(PostTag.id == search_params.tag_id)

        if search_params.tag_slug:
            stmt = stmt.join(Post.tags).filter(PostTag.slug == search_params.tag_slug)

        if search_params.author_id:
            stmt = stmt.filter(Post.author_id == search_params.author_id)

        if search_params.status:
            stmt = stmt.filter(Post.status == search_params.status)

        if search_params.is_published is not None:
            stmt = stmt.filter(Post.is_published == search_params.is_published)

        if search_params.is_featured is not None:
            stmt = stmt.filter(Post.is_featured == search_params.is_featured)

        if search_params.is_pinned is not None:
            stmt = stmt.filter(Post.is_pinned == search_params.is_pinned)

        if search_params.date_from:
            stmt = stmt.filter(Post.published_at >= search_params.date_from)

        if search_params.date_to:
            stmt = stmt.filter(Post.published_at <= search_params.date_to)

        return stmt

    async def get_featured_posts(self, limit: int = 6) -> List[Post]:
        """Получить рекомендуемые посты"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(and_(Post.is_featured == True, Post.is_published == True))
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        # Добавляем featured_media для каждого поста
        for post in posts:
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return posts

    async def get_recent_posts(self, limit: int = 12) -> List[Post]:
        """Получить последние опубликованные посты"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(Post.is_published == True)
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        # Добавляем featured_media для каждого поста
        for post in posts:
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return posts

    async def get_pinned_posts(self) -> List[Post]:
        """Получить закрепленные посты"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(and_(Post.is_pinned == True, Post.is_published == True))
            .order_by(desc(Post.published_at))
        )
        
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        # Добавляем featured_media для каждого поста
        for post in posts:
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return posts

    async def get_popular_posts(self, limit: int = 10) -> List[Post]:
        """Получить популярные посты по количеству просмотров"""
        stmt = (
            select(Post)
            .options(
                joinedload(Post.author),
                joinedload(Post.tags),
                selectinload(Post.media)
            )
            .filter(Post.is_published == True)
            .order_by(desc(Post.views_count))
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        # Добавляем featured_media для каждого поста
        for post in posts:
            setattr(post, 'featured_media', self._get_featured_media(post))
        
        return posts

    async def create_post(self, post_data: PostCreate) -> Post:
        """Создать новый пост"""
        try:
            # Создаем пост
            post = Post(
                title=post_data.title,
                slug=post_data.slug,
                excerpt=post_data.excerpt,
                content=post_data.content,
                meta_title=post_data.meta_title,
                meta_description=post_data.meta_description,
                meta_keywords=post_data.meta_keywords,
                status=post_data.status,
                is_published=post_data.is_published,
                is_featured=post_data.is_featured,
                is_pinned=post_data.is_pinned,
                author_id=post_data.author_id,
                published_at=post_data.published_at or (datetime.utcnow() if post_data.is_published else None),
                extra_data=post_data.extra_data
            )

            self.db.add(post)
            await self.db.flush()

            # Добавляем теги
            if post_data.tag_ids:
                stmt = select(PostTag).filter(PostTag.id.in_(post_data.tag_ids))
                result = await self.db.execute(stmt)
                tags = result.scalars().all()
                post.tags = tags

            await self.db.commit()
            await self.db.refresh(post)

            return await self.get_post(post.id)

        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Пост с таким slug уже существует")

    async def update_post(self, post_id: int, post_data: PostUpdate) -> Optional[Post]:
        """Обновить пост"""
        stmt = select(Post).filter(Post.id == post_id)
        result = await self.db.execute(stmt)
        post = result.scalar()
        
        if not post:
            return None

        try:
            # Обновляем поля
            update_data = post_data.model_dump(exclude_unset=True)
            
            # Обрабатываем теги отдельно
            tag_ids = update_data.pop('tag_ids', None)
            
            for field, value in update_data.items():
                setattr(post, field, value)

            # Обновляем теги
            if tag_ids is not None:
                stmt = select(PostTag).filter(PostTag.id.in_(tag_ids))
                result = await self.db.execute(stmt)
                tags = result.scalars().all()
                post.tags = tags

            # Устанавливаем дату публикации
            if post_data.is_published and not post.published_at:
                post.published_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(post)

            return await self.get_post(post.id)

        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Пост с таким slug уже существует")

    async def delete_post(self, post_id: int) -> bool:
        """Удалить пост"""
        stmt = select(Post).filter(Post.id == post_id)
        result = await self.db.execute(stmt)
        post = result.scalar()
        
        if not post:
            return False

        await self.db.delete(post)
        await self.db.commit()
        return True

    # === POST TAGS ===

    async def get_popular_tags(self, limit: int = 8) -> List[PostTag]:
        """Получить популярные теги"""
        stmt = (
            select(PostTag)
            .filter(PostTag.is_active == True)
            .order_by(desc(PostTag.posts_count))
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_tag_by_slug(self, slug: str) -> Optional[PostTag]:
        """Получить тег по slug"""
        stmt = select(PostTag).filter(PostTag.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar()

    async def create_tag(self, tag_data: PostTagCreate) -> PostTag:
        """Создать новый тег"""
        tag = PostTag(**tag_data.model_dump())
        self.db.add(tag)
        await self.db.commit()
        await self.db.refresh(tag)
        return tag

    async def update_tag_posts_count(self, tag_id: int):
        """Обновить количество постов для тега"""
        count_stmt = (
            select(func.count(post_tags_association.c.post_id))
            .filter(post_tags_association.c.tag_id == tag_id)
        )
        
        count_result = await self.db.execute(count_stmt)
        count = count_result.scalar()
        
        update_stmt = (
            select(PostTag)
            .filter(PostTag.id == tag_id)
        )
        result = await self.db.execute(update_stmt)
        tag = result.scalar()
        
        if tag:
            tag.posts_count = count
            await self.db.commit()

    # === POST AUTHORS ===

    async def get_author(self, author_id: int) -> Optional[PostAuthor]:
        """Получить автора по ID"""
        stmt = select(PostAuthor).filter(PostAuthor.id == author_id)
        result = await self.db.execute(stmt)
        return result.scalar()

    async def create_author(self, author_data: PostAuthorCreate) -> PostAuthor:
        """Создать нового автора"""
        author = PostAuthor(**author_data.model_dump())
        self.db.add(author)
        await self.db.commit()
        await self.db.refresh(author)
        return author

    # === POST MEDIA ===

    async def create_media(self, media_data: PostMediaCreate) -> PostMedia:
        """Создать медиа для поста"""
        media = PostMedia(**media_data.model_dump())
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)
        return media

    async def get_post_media(self, post_id: int) -> List[PostMedia]:
        """Получить все медиа поста"""
        stmt = (
            select(PostMedia)
            .filter(PostMedia.post_id == post_id)
            .order_by(PostMedia.order)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # === STATISTICS ===

    async def track_view(self, view_data: PostViewCreate) -> PostView:
        """Отследить просмотр поста"""
        # Проверяем, не было ли уже просмотра от этого IP/сессии недавно
        existing_stmt = (
            select(PostView)
            .filter(
                and_(
                    PostView.post_id == view_data.post_id,
                    PostView.ip_address == view_data.ip_address,
                    PostView.viewed_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                )
            )
        )
        
        existing_result = await self.db.execute(existing_stmt)
        existing_view = existing_result.scalar()

        if not existing_view:
            # Создаем запись о просмотре
            view = PostView(**view_data.model_dump())
            self.db.add(view)

            # Увеличиваем счетчик просмотров поста
            post_stmt = select(Post).filter(Post.id == view_data.post_id)
            post_result = await self.db.execute(post_stmt)
            post = post_result.scalar()
            
            if post:
                post.views_count = post.views_count + 1

            await self.db.commit()
            await self.db.refresh(view)
            return view

        return existing_view

    async def add_like(self, like_data: PostLikeCreate) -> Optional[PostLike]:
        """Добавить лайк посту"""
        # Проверяем, не лайкал ли уже этот IP/сессия
        existing_stmt = (
            select(PostLike)
            .filter(
                and_(
                    PostLike.post_id == like_data.post_id,
                    PostLike.ip_address == like_data.ip_address
                )
            )
        )
        
        existing_result = await self.db.execute(existing_stmt)
        existing_like = existing_result.scalar()

        if not existing_like:
            # Создаем лайк
            like = PostLike(**like_data.model_dump())
            self.db.add(like)

            # Увеличиваем счетчик лайков поста
            post_stmt = select(Post).filter(Post.id == like_data.post_id)
            post_result = await self.db.execute(post_stmt)
            post = post_result.scalar()
            
            if post:
                post.likes_count = post.likes_count + 1

            await self.db.commit()
            await self.db.refresh(like)
            return like

        return None


def get_posts_crud(db: AsyncSession) -> PostsCRUD:
    """Фабрика для создания CRUD объекта"""
    return PostsCRUD(db)