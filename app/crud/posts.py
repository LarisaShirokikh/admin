# app/crud/posts.py

from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import and_, or_, desc, asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError

from app.models.posts import Post, PostAuthor, PostTag, PostMedia, PostView, PostLike, post_tags_association
from app.schemas.posts import (
    PostCreate, PostUpdate, PostSearchParams,
    PostAuthorCreate, PostTagCreate,
    PostMediaCreate, PostViewCreate, PostLikeCreate,
)


class PostsCRUD:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Helpers ──

    @staticmethod
    def _get_featured_media(post: Post) -> Optional[PostMedia]:
        if not post.media:
            return None
        for item in post.media:
            if item.is_featured:
                return item
        return post.media[0] if post.media else None

    @staticmethod
    def _base_query():
        return (
            select(Post)
            .options(
                joinedload(Post.author),
                selectinload(Post.tags),
                selectinload(Post.media),
            )
        )

    def _enrich(self, post: Post) -> Post:
        setattr(post, "featured_media", self._get_featured_media(post))
        return post

    def _enrich_many(self, posts: List[Post]) -> List[Post]:
        for p in posts:
            self._enrich(p)
        return posts

    def _apply_filters(self, stmt, params: PostSearchParams):
        if params.q:
            term = f"%{params.q}%"
            stmt = stmt.filter(
                or_(
                    Post.title.ilike(term),
                    Post.excerpt.ilike(term),
                    Post.content.ilike(term),
                )
            )
        if params.tag_id:
            stmt = stmt.join(Post.tags).filter(PostTag.id == params.tag_id)
        if params.tag_slug:
            stmt = stmt.join(Post.tags).filter(PostTag.slug == params.tag_slug)
        if params.author_id:
            stmt = stmt.filter(Post.author_id == params.author_id)
        if params.status:
            stmt = stmt.filter(Post.status == params.status)
        if params.is_published is not None:
            stmt = stmt.filter(Post.is_published == params.is_published)
        if params.is_featured is not None:
            stmt = stmt.filter(Post.is_featured == params.is_featured)
        if params.is_pinned is not None:
            stmt = stmt.filter(Post.is_pinned == params.is_pinned)
        if params.date_from:
            stmt = stmt.filter(Post.published_at >= params.date_from)
        if params.date_to:
            stmt = stmt.filter(Post.published_at <= params.date_to)
        return stmt

    # ── Posts ──

    async def get_post(self, post_id: int) -> Optional[Post]:
        result = await self.db.execute(
            self._base_query().filter(Post.id == post_id)
        )
        post = result.scalar()
        return self._enrich(post) if post else None

    async def get_post_by_slug(self, slug: str) -> Optional[Post]:
        result = await self.db.execute(
            self._base_query().filter(Post.slug == slug)
        )
        post = result.scalar()
        return self._enrich(post) if post else None

    async def get_posts(
        self,
        skip: int = 0,
        limit: int = 20,
        search_params: Optional[PostSearchParams] = None,
    ) -> Tuple[List[Post], int]:
        stmt = self._base_query()
        if search_params:
            stmt = self._apply_filters(stmt, search_params)

        total = (await self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar()

        order_field = getattr(Post, search_params.order_by, Post.created_at) if search_params else Post.created_at
        order_dir = search_params.order_dir if search_params else "desc"
        stmt = stmt.order_by(asc(order_field) if order_dir == "asc" else desc(order_field))
        stmt = stmt.offset(skip).limit(limit)

        result = await self.db.execute(stmt)
        posts = result.unique().scalars().all()
        return self._enrich_many(list(posts)), total

    async def get_featured_posts(self, limit: int = 6) -> List[Post]:
        result = await self.db.execute(
            self._base_query()
            .filter(Post.is_featured == True, Post.is_published == True)
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        return self._enrich_many(list(result.unique().scalars().all()))

    async def get_recent_posts(self, limit: int = 12) -> List[Post]:
        result = await self.db.execute(
            self._base_query()
            .filter(Post.is_published == True)
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        return self._enrich_many(list(result.unique().scalars().all()))

    async def get_pinned_posts(self) -> List[Post]:
        result = await self.db.execute(
            self._base_query()
            .filter(Post.is_pinned == True, Post.is_published == True)
            .order_by(desc(Post.published_at))
        )
        return self._enrich_many(list(result.unique().scalars().all()))

    async def get_popular_posts(self, limit: int = 10) -> List[Post]:
        result = await self.db.execute(
            self._base_query()
            .filter(Post.is_published == True)
            .order_by(desc(Post.views_count))
            .limit(limit)
        )
        return self._enrich_many(list(result.unique().scalars().all()))

    async def create_post(self, data: PostCreate) -> Post:
        try:
            # Load tags first: assigning post.tags after flush() would trigger a
            # sync lazy-load of the collection inside the async context (MissingGreenlet).
            tags = []
            if data.tag_ids:
                tags_result = await self.db.execute(
                    select(PostTag).filter(PostTag.id.in_(data.tag_ids))
                )
                tags = list(tags_result.unique().scalars().all())

            post = Post(
                title=data.title,
                slug=data.slug,
                excerpt=data.excerpt,
                content=data.content,
                meta_title=data.meta_title,
                meta_description=data.meta_description,
                meta_keywords=data.meta_keywords,
                status=data.status,
                is_published=data.is_published,
                is_featured=data.is_featured,
                is_pinned=data.is_pinned,
                author_id=data.author_id,
                published_at=data.published_at or (datetime.utcnow() if data.is_published else None),
                extra_data=data.extra_data,
                tags=tags,
            )
            self.db.add(post)
            await self.db.commit()
            return await self.get_post(post.id)

        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Post with this slug already exists")

    async def update_post(self, post_id: int, data: PostUpdate) -> Optional[Post]:
        result = await self.db.execute(
            self._base_query().filter(Post.id == post_id)
        )
        post = result.unique().scalar()
        if not post:
            return None

        try:
            update_data = data.model_dump(exclude_unset=True)
            tag_ids = update_data.pop("tag_ids", None)

            for field, value in update_data.items():
                setattr(post, field, value)

            if tag_ids is not None:
                tags_result = await self.db.execute(
                    select(PostTag).filter(PostTag.id.in_(tag_ids))
                )
                post.tags = list(tags_result.unique().scalars().all())

            if data.is_published and not post.published_at:
                post.published_at = datetime.utcnow()

            await self.db.commit()
            return await self.get_post(post.id)

        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Post with this slug already exists")

    async def delete_post(self, post_id: int) -> bool:
        result = await self.db.execute(select(Post).filter(Post.id == post_id))
        post = result.scalar()
        if not post:
            return False
        await self.db.delete(post)
        await self.db.commit()
        return True

    # ── Tags ──

    async def get_popular_tags(self, limit: int = 8) -> List[PostTag]:
        result = await self.db.execute(
            select(PostTag)
            .filter(PostTag.is_active == True)
            .order_by(desc(PostTag.posts_count))
            .limit(limit)
        )
        return list(result.unique().scalars().all())

    async def get_tag_by_slug(self, slug: str) -> Optional[PostTag]:
        result = await self.db.execute(
            select(PostTag).filter(PostTag.slug == slug)
        )
        return result.scalar()

    async def create_tag(self, data: PostTagCreate) -> PostTag:
        # Return existing tag if name already exists
        existing = (await self.db.execute(
            select(PostTag).filter(PostTag.name == data.name)
        )).scalar()
        if existing:
            return existing

        try:
            tag = PostTag(**data.model_dump())
            self.db.add(tag)
            await self.db.commit()
            await self.db.refresh(tag)
            return tag
        except IntegrityError:
            await self.db.rollback()
            result = (await self.db.execute(
                select(PostTag).filter(PostTag.name == data.name)
            )).scalar()
            return result

    # ── Authors ──

    async def get_author(self, author_id: int) -> Optional[PostAuthor]:
        result = await self.db.execute(
            select(PostAuthor).filter(PostAuthor.id == author_id)
        )
        return result.scalar()

    async def create_author(self, data: PostAuthorCreate) -> PostAuthor:
        author = PostAuthor(**data.model_dump())
        self.db.add(author)
        await self.db.commit()
        await self.db.refresh(author)
        return author

    # ── Media ──

    async def create_media(self, data: PostMediaCreate) -> PostMedia:
        media = PostMedia(**data.model_dump())
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)
        return media

    async def get_post_media(self, post_id: int) -> List[PostMedia]:
        result = await self.db.execute(
            select(PostMedia)
            .filter(PostMedia.post_id == post_id)
            .order_by(PostMedia.order)
        )
        return list(result.unique().scalars().all())

    # ── Stats ──

    async def track_view(self, data: PostViewCreate) -> PostView:
        existing = (await self.db.execute(
            select(PostView).filter(
                PostView.post_id == data.post_id,
                PostView.ip_address == data.ip_address,
                PostView.viewed_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )).scalar()

        if existing:
            return existing

        view = PostView(**data.model_dump())
        self.db.add(view)

        post = (await self.db.execute(
            select(Post).filter(Post.id == data.post_id)
        )).scalar()
        if post:
            post.views_count += 1

        await self.db.commit()
        await self.db.refresh(view)
        return view

    async def add_like(self, data: PostLikeCreate) -> Optional[PostLike]:
        existing = (await self.db.execute(
            select(PostLike).filter(
                PostLike.post_id == data.post_id,
                PostLike.ip_address == data.ip_address,
            )
        )).scalar()

        if existing:
            return None

        like = PostLike(**data.model_dump())
        self.db.add(like)

        post = (await self.db.execute(
            select(Post).filter(Post.id == data.post_id)
        )).scalar()
        if post:
            post.likes_count += 1

        await self.db.commit()
        await self.db.refresh(like)
        return like


def get_posts_crud(db: AsyncSession) -> PostsCRUD:
    return PostsCRUD(db)