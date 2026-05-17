import os

# Set required env vars before any app module is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")
