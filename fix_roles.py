import asyncio
import asyncpg

async def fix_user_roles():
    conn = await asyncpg.connect(
        'postgresql://ai_hub_user:my_secure_password@localhost:5432/ai_learning_hub_db'
    )
    
    rows = await conn.fetch('SELECT id, email, role FROM users')
    print(f"Found {len(rows)} users")
    for row in rows:
        print(f"User {row['email']}: role={row['role']}")
    
    await conn.execute("UPDATE users SET role = 'student' WHERE role NOT IN ('admin', 'lecturer', 'student')")
    print("Updated invalid roles to 'student'")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_user_roles())