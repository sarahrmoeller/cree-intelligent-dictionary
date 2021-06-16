from django.conf import settings


def morphodict_titles(request):
    language_pair = getattr(settings, "MORPHODICT_SOURCE_LANGUAGE", "???") + getattr(
        settings, "MORPHODICT_TARGET_LANGUAGE", "???"
    )

    return {
        "MORPHODICT_SITE_TITLE": getattr(
            settings, "MORPHODICT_SITE_TITLE", language_pair
        ),
        "MORPHODICT_SITE_SUBTITLE": getattr(
            settings, "MORPHODICT_SITE_SUBTITLE", f"Morphodict"
        ),
    }
