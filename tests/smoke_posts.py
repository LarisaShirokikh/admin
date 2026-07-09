import asyncio, sys, faulthandler
faulthandler.dump_traceback_later(20, exit=True)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

def ck(msg):
    print(msg, flush=True)

async def main():
    ck("1: import models")
    from app.core.database import Base
    from app.crud.posts import get_posts_crud
    from app.schemas.posts import (PostCreate, PostUpdate, PostSearchParams,
                                   PostAuthorCreate, PostTagCreate, PostViewCreate, PostLikeCreate)
    import app.models  # ensure all tables registered

    ck("2: create engine + tables")
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)

    ck("3: session")
    S = async_sessionmaker(eng, expire_on_commit=False)
    async with S() as db:
        crud = get_posts_crud(db)
        ck("4: author+tags")
        a = await crud.create_author(PostAuthorCreate(name="Лариса", slug="larisa", email="larisa@test.ru"))
        t = await crud.create_tag(PostTagCreate(name="Двери", slug="dveri"))
        t2 = await crud.create_tag(PostTagCreate(name="Двери", slug="dveri-dup"))
        assert t2.id == t.id, "tag dedup failed"
        ck("5: create_post")
        p = await crud.create_post(PostCreate(title="Тест", slug="test", content="hello",
                                              is_published=True, author_id=a.id, tag_ids=[t.id]))
        assert p.author.name == "Лариса" and p.tags[0].slug == "dveri"
        ck("6: get_by_slug")
        by_slug = await crud.get_post_by_slug("test")
        assert by_slug and by_slug.id == p.id
        ck("7: dup slug")
        try:
            await crud.create_post(PostCreate(title="X", slug="test", content="x"))
            raise SystemExit("dup slug not caught")
        except ValueError:
            pass
        ck("8: update")
        up = await crud.update_post(p.id, PostUpdate(title="Тест2", tag_ids=[]))
        assert up.title == "Тест2" and list(up.tags) == []
        ck("9: search")
        posts, total = await crud.get_posts(search_params=PostSearchParams(q="Тест", is_published=True))
        assert total == 1, f"search total={total}"
        ck("10: views")
        v = await crud.track_view(PostViewCreate(post_id=p.id, ip_address="1.2.3.4"))
        v2 = await crud.track_view(PostViewCreate(post_id=p.id, ip_address="1.2.3.4"))
        assert v.id == v2.id
        ck("11: likes")
        l1 = await crud.add_like(PostLikeCreate(post_id=p.id, ip_address="1.2.3.4"))
        l2 = await crud.add_like(PostLikeCreate(post_id=p.id, ip_address="1.2.3.4"))
        assert l1 and l2 is None
        ck("12: counters")
        fresh = await crud.get_post(p.id)
        assert fresh.views_count == 1 and fresh.likes_count == 1
        ck("13: delete")
        assert await crud.delete_post(p.id) is True
        assert await crud.get_post(p.id) is None
        print("SMOKE TEST: все проверки прошли ✅", flush=True)

asyncio.run(main())

import os; os._exit(0)
