import asyncio
from sqlalchemy.future import select
from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.user import User
from app.models.quota import Quota

async def init_db() -> None:
    async with async_session_factory() as session:
        # Check if admin user already exists
        result = await session.execute(select(User).filter_by(email="admin@learninghub.com"))
        admin_user = result.scalars().first()
        
        if not admin_user:
            print("Seeding default administrator...")
            admin_user = User(
                email="admin@learninghub.com",
                password_hash=hash_password("admin123"),
                full_name="System Administrator",
                role="admin",
                is_active=True
            )
            session.add(admin_user)
            await session.flush()  # Obtain the admin_user.id
            
            # Check if quota exists for this user
            quota = Quota(
                user_id=admin_user.id,
                storage_limit_mb=10240, # 10 GB
                storage_used_mb=0,
                video_limit=50,
                video_used=0,
                token_limit=500000,
                token_used=0
            )
            session.add(quota)
            await session.commit()
            print("Default administrator and quotas seeded successfully!")
        else:
            print("Administrator already seeded.")

if __name__ == "__main__":
    asyncio.run(init_db())
