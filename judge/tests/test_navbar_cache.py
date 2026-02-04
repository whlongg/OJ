from django.core.cache import cache
from django.test import TestCase

from judge.models import NavigationBar


class NavigationBarCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_navbar_cache_invalidates_on_save(self):
        NavigationBar.objects.create(
            order=1,
            key='home',
            label='Home',
            path='/',
            regex=r'^/$',
        )

        from judge.utils.caching import get_cached_navbar

        nav_bar = get_cached_navbar()
        self.assertEqual(len(nav_bar), 1)

        NavigationBar.objects.create(
            order=2,
            key='problems',
            label='Problems',
            path='/problems/',
            regex=r'^/problems/',
        )

        nav_bar = get_cached_navbar()
        self.assertEqual(len(nav_bar), 2)

    def test_nav_tab_cache_invalidates_on_save(self):
        item = NavigationBar.objects.create(
            order=1,
            key='home',
            label='Home',
            path='/foo/',
            regex=r'^/foo',
        )

        from judge.utils.caching import get_cached_nav_tab

        keys = get_cached_nav_tab('/foo')
        self.assertIn('home', keys)

        item.regex = r'^/bar'
        item.save(update_fields=['regex'])

        keys = get_cached_nav_tab('/foo')
        self.assertEqual(keys, [])
