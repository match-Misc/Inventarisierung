from django.conf import settings


def branding(request):
    return {"app_site_name": settings.SITE_NAME}
