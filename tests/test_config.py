from app.core.config import REQUIRED_CORS_ORIGINS, Settings


def test_required_frontend_origins_are_always_allowed():
    settings = Settings(
        CORS_ORIGINS='["http://localhost:5173"]',
        DEBUG=True,
        SECRET_KEY="test_secret_key_that_is_long_enough_for_validation",
        INTERNAL_API_KEY="test_internal_key_that_is_long_enough",
    )

    assert REQUIRED_CORS_ORIGINS.issubset(set(settings.CORS_ORIGINS))
    assert "http://localhost:5173" in settings.CORS_ORIGINS


def test_cors_origins_are_normalized_without_trailing_slashes():
    settings = Settings(
        CORS_ORIGINS="https://example.com/, https://learninghubs.tech/",
        DEBUG=True,
        SECRET_KEY="test_secret_key_that_is_long_enough_for_validation",
        INTERNAL_API_KEY="test_internal_key_that_is_long_enough",
    )

    assert "https://example.com" in settings.CORS_ORIGINS
    assert all(not origin.endswith("/") for origin in settings.CORS_ORIGINS)


def test_ai_service_timeout_setting_default_and_custom():
    settings_default = Settings(
        DEBUG=True,
        SECRET_KEY="test_secret_key_that_is_long_enough_for_validation",
        INTERNAL_API_KEY="test_internal_key_that_is_long_enough",
    )
    assert settings_default.AI_SERVICE_TIMEOUT == 30.0

    settings_custom = Settings(
        DEBUG=True,
        SECRET_KEY="test_secret_key_that_is_long_enough_for_validation",
        INTERNAL_API_KEY="test_internal_key_that_is_long_enough",
        AI_SERVICE_TIMEOUT=45.5,
    )
    assert settings_custom.AI_SERVICE_TIMEOUT == 45.5

