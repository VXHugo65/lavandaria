from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
import django_heroku
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-cd1lm6+^+94&zml-#rvc_wlumv*yht#3g2+)zfkmy!u7l))9o%'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    "unfold",  # before django.contrib.admin
    "unfold.contrib.filters",  # optional, if special filters are needed
    "unfold.contrib.forms",  # optional, if special form elements are needed
    "unfold.contrib.inlines",  # optional, if special inlines are needed
    "unfold.contrib.import_export",  # optional, if django-import-export package is used
    "unfold.contrib.simple_history",  # optional, if django-simple-history package is used


    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "core.apps.CoreConfig",
    "import_export"

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Lavandaria.urls'

CSRF_TRUSTED_ORIGINS = [
    'https://lavandaria.up.railway.app',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Lavandaria.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'
MEDIA_URL = '/images/service/'

STATICFILES_DIRS = [
    BASE_DIR / 'static'
]
MEDIA_ROOT = BASE_DIR / 'static/images/service'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
django_heroku.settings(locals())


UNFOLD = {
    "SITE_TITLE": "Lavandaria",
    "SITE_HEADER": "Lavandaria",
    "SITE_URL": "/",
    "SITE_SYMBOL": "local_laundry_service",  # symbol from icon set

    "SHOW_HISTORY": True, # show/hide "History" button, default: True
    "SHOW_VIEW_ON_SITE": False, # show/hide "View on site" button, default: True
    # "DASHBOARD_CALLBACK": "core.admin.dashboard_callback",

    "SIDEBAR": {
        "show_search": True,  # Search in applications and models names
        "show_all_applications": True,  # Dropdown with all applications and models
        "navigation": [
            {
                "separator": False,  # Top border
                "collapsible": False,  # Collapsible group of links
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:index"),
                    },

                ],
            },
            {
                "title": _("View applications"),
                "separator": False,
                "collapsible": False,
                "items": [

                    {
                        "title": _("Lavandaria"),
                        "icon": "store",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_lavandaria_changelist"),  # Link para a lista de Suppliers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Funcionario"),
                        "icon": "person",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_funcionario_changelist"),  # Link para a lista de Suppliers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Servico"),
                        "icon": "dry_cleaning",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_servico_changelist"),  # Link para a lista de Customers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Item de servico"),
                        "icon": "category",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_itemservico_changelist"),  # Link para a lista de Customers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Cliente"),
                        "icon": "handshake",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_cliente_changelist"),  # Link para a lista de Customers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Atendimento"),
                        "icon": "shopping_cart",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_pedido_changelist"),  # Link para a lista de Customers
                        "permission": lambda request: request.user.is_superuser,
                    },
                    # {
                    #     "title": _("Pedido"),
                    #     "icon": "shopping_cart",  # Supported icon set: https://fonts.google.com/icons
                    #     "link": reverse_lazy("admin:core_pedido_add"),  # Link para a lista de Customers
                    #     "permission": lambda request: request.user.is_superuser,
                    # },

                ]
            }
        ],
    },

}

