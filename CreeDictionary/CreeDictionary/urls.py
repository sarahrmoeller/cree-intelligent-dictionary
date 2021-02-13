"""
Definition of urls for CreeDictionary.
"""

import os

import API.views as api_views
from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django_js_reverse.views import urls_js

from CreeDictionary import views

urlpatterns = [
    # user interface
    path("", views.index, name="cree-dictionary-index"),
    path("search", views.index, name="cree-dictionary-search"),
    # DEPRECATED: this route 👇 is a permanent redirect to the route above ☝️
    path(
        "search/<str:query_string>/",
        views.redirect_search,
        name="cree-dictionary-index-with-query",
    ),
    # word is a user-friendly alternative for the linguistic term "lemma"
    path(
        "word/<str:lemma_text>/",
        views.lemma_details,
        name="cree-dictionary-index-with-lemma",
    ),
    path("about", views.about, name="cree-dictionary-about"),
    path("contact-us", views.contact_us, name="cree-dictionary-contact-us"),
    # internal use to render boxes of search results
    path(
        "_search_results/<str:query_string>/",
        views.search_results,
        name="cree-dictionary-search-results",
    ),
    # internal use to render paradigm and only the paradigm
    path(
        "_paradigm_details/",
        views.paradigm_internal,
        name="cree-dictionary-paradigm-detail",
    ),
    # cree word translation for click-in-text
    path(
        "click-in-text/",
        api_views.click_in_text,
        name="cree-dictionary-word-click-in-text-api",
    ),
    path("admin/", admin.site.urls),
    path(
        "",
        include("morphodict.urls"),
        name="cree-dictionary-change-orthography",
    ),
    path("search-quality/", include("search_quality.urls")),
]

# Add style debugger, but only in DEBUG mode!
if settings.DEBUG:
    urlpatterns.append(path("styles", views.styles, name="styles"))

# Reverse URLs in JavaScript:  https://github.com/ierror/django-js-reverse
urlpatterns.append(url(fr"^jsreverse/$", urls_js, name="js_reverse"))

if settings.DEBUG:
    # saves the need to `manage.py collectstatic` in development
    urlpatterns += staticfiles_urlpatterns()

if settings.DEBUG and settings.ENABLE_DJANGO_DEBUG_TOOLBAR:
    import debug_toolbar

    # necessary for debug_toolbar to work
    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
