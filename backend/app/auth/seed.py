"""Idempotent first-admin seeding from environment."""
from . import service
from .models import ROLE_SUPERADMIN
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.auth")


def seed_admin_from_env():
    if service.count_superadmins() > 0:
        return None
    if not Config.ADMIN_EMAIL or not Config.ADMIN_PASSWORD:
        logger.warning(
            "No superadmin exists and ADMIN_EMAIL/ADMIN_PASSWORD are unset — "
            "create a superadmin before using the app.")
        return None
    uid = service.create_user(Config.ADMIN_EMAIL, Config.ADMIN_PASSWORD,
                              role=ROLE_SUPERADMIN, account_id=None)
    logger.info("Seeded initial superadmin %s", Config.ADMIN_EMAIL)
    return uid
