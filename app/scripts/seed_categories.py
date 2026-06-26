"""
Seed script for initial categories.
Run after migration: python -m app.scripts.seed_categories
"""

import re
import uuid
from datetime import datetime, timezone

CATEGORIES = [
    ("Lập trình", "Các khóa học về lập trình và phát triển phần mềm", "💻"),
    ("Trí tuệ nhân tạo", "AI, Machine Learning, Deep Learning và Data Science", "🤖"),
    ("Kinh doanh", "Quản lý, marketing, tài chính và khởi nghiệp", "💼"),
    ("Thiết kế", "UI/UX, đồ họa, nhiếp ảnh và sáng tạo", "🎨"),
    ("Ngôn ngữ", "Học tiếng Anh, tiếng Nhật và các ngôn ngữ khác", "🌍"),
    ("Kỹ năng mềm", "Giao tiếp, lãnh đạo và phát triển cá nhân", "🌟"),
    ("Tài chính", "Đầu tư, chứng khoán và quản lý tài chính", "📈"),
    ("Marketing", "Digital marketing, SEO, content và social media", "📢"),
]


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug


if __name__ == "__main__":
    import asyncio
    import asyncpg
    import os

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ai_hub_user:my_secure_password@localhost:5432/ai_learning_hub_db"
    ).replace("postgresql+asyncpg://", "postgresql://")

    async def seed():
        conn = await asyncpg.connect(DATABASE_URL)

        existing = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if existing > 0:
            print(f"Categories already seeded ({existing} found), skipping...")
            await conn.close()
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for name, description, icon in CATEGORIES:
            cat_id = str(uuid.uuid4())
            slug = slugify(name)
            await conn.execute(
                """
                INSERT INTO categories (id, name, slug, description, icon, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                cat_id, name, slug, description, icon, now
            )
        print(f"Seeded {len(CATEGORIES)} categories successfully!")

        await conn.close()

    asyncio.run(seed())