import hashlib

from django.core.cache import cache

from judge.models import NavigationBar

NAVBAR_CACHE_KEY = 'navbar_tree'
NAVBAR_CACHE_TTL = 86400
NAV_TAB_VERSION_KEY = 'nav_tab_version'
NAV_TAB_CACHE_TTL = 86400


def _get_nav_tab_version():
    version = cache.get(NAV_TAB_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(NAV_TAB_VERSION_KEY, version, NAV_TAB_CACHE_TTL)
    return version


def bump_nav_tab_version():
    version = cache.get(NAV_TAB_VERSION_KEY)
    if version is None:
        version = 1
    cache.set(NAV_TAB_VERSION_KEY, version + 1, NAV_TAB_CACHE_TTL)


def get_cached_navbar():
    nav_bar = cache.get(NAVBAR_CACHE_KEY)
    if nav_bar is None:
        nav_bar = list(NavigationBar.objects.all())
        cache.set(NAVBAR_CACHE_KEY, nav_bar, NAVBAR_CACHE_TTL)
    return nav_bar


def get_cached_nav_tab(path):
    version = _get_nav_tab_version()
    path_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
    cache_key = f'nav_tab:{version}:{path_hash}'
    nav_tab = cache.get(cache_key)
    if nav_tab is None:
        result = list(NavigationBar.objects.extra(where=['%s REGEXP BINARY regex'], params=[path])[:1])
        nav_tab = list(result[0].get_ancestors(include_self=True).values_list('key', flat=True)) if result else []
        cache.set(cache_key, nav_tab, NAV_TAB_CACHE_TTL)
    return nav_tab
