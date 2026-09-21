from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class Hasher:
    @staticmethod
    async def verify_password(input_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(input_password, hashed_password)

    @staticmethod
    async def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)
