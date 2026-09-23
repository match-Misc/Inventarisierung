"""Django-Einstellungen. Alle umgebungsabhängigen Werte kommen aus Umgebungsvariablen (siehe .env.example)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)
# Nur für die Entwicklung. Im Betrieb muss SECRET_KEY gesetzt sein (compose.yaml erzwingt das).
SECRET_KEY = env("SECRET_KEY", default="django-insecure-nur-fuer-die-entwicklung")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SITE_NAME = env("SITE_NAME", default="Geräteinventar")
# Basis-URL für Links in E-Mails, z. B. https://inventar.example.org
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_filters",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_htmx",
    "accounts",
    "inventory",
    "loans",
    "assistant_search",
    "floorplan",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Ohne Anmeldung ist nichts erreichbar (Ausnahmen: Login- und Passwort-Seiten).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "loans.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
# Gültigkeit von Passwort-Reset- und Einladungslinks
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 7

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "de"
TIME_ZONE = env("TIME_ZONE", default="Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Hochgeladene Dateien werden nur über inventory.views.serve_media ausgeliefert (Login nötig).
MEDIA_URL = "/medien/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MAX_PHOTO_UPLOAD_MB = env.int("MAX_PHOTO_UPLOAD_MB", default=25)
MAX_DOCUMENT_UPLOAD_MB = env.int("MAX_DOCUMENT_UPLOAD_MB", default=100)

# E-Mail, z. B. EMAIL_URL=smtp+tls://benutzer:passwort@smtp.example.org:587
# Ohne EMAIL_URL werden Mails nur auf der Konsole ausgegeben.
vars().update(env.email_url("EMAIL_URL", default="consolemail://"))
# Entwicklung: Mails als Dateien ablegen, um sie ansehen zu können (z. B. EMAIL_FILE_PATH=sent_emails)
if env("EMAIL_FILE_PATH", default="") and not env("EMAIL_URL", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = BASE_DIR / env("EMAIL_FILE_PATH")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"{SITE_NAME} <inventar@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Ausleihe und Erinnerungen
DEFAULT_LOAN_DAYS = env.int("DEFAULT_LOAN_DAYS", default=7)
REMINDER_OVERDUE_INTERVAL_DAYS = env.int("REMINDER_OVERDUE_INTERVAL_DAYS", default=2)
REMINDER_PENDING_REQUEST_DAYS = env.int("REMINDER_PENDING_REQUEST_DAYS", default=2)

# Der Schlüssel bleibt ausschließlich in der Serverumgebung.
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
ASSISTANT_MODEL = env("ASSISTANT_MODEL", default="openai/gpt-6-luna")
ITEM_RECOGNITION_MODELS = {
    "easy": env("ITEM_RECOGNITION_MODEL_EASY", default="openai/gpt-4.1-nano"),
    "medium": env("ITEM_RECOGNITION_MODEL_MEDIUM", default="openai/gpt-4.1-mini"),
    "hard": env("ITEM_RECOGNITION_MODEL_HARD", default="openai/gpt-4.1"),
}
ASSISTANT_WEB_SEARCH = env.bool("ASSISTANT_WEB_SEARCH", default=True)
ASSISTANT_REQUESTS_PER_HOUR = env.int("ASSISTANT_REQUESTS_PER_HOUR", default=20)

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Betrieb hinter einem HTTPS-Reverse-Proxy, der X-Forwarded-Proto setzt.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
# Für ein internes Tool ist die HSTS-Preload-Liste der Browser nicht sinnvoll.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
MESSAGE_TAGS = {40: "danger"}  # messages.ERROR -> Bootstrap-Klasse "danger"
