import re
import random
import string

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CASCADE, F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from judge.models.profile import Organization, Profile

__all__ = ['MiscConfig', 'validate_regex', 'NavigationBar', 'BlogPost', 'URLShortener']


class MiscConfig(models.Model):
    key = models.CharField(max_length=30, verbose_name=_('key'), db_index=True)
    value = models.TextField(verbose_name=_('value'), blank=True)

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = _('configuration item')
        verbose_name_plural = _('miscellaneous configuration')


def validate_regex(regex):
    try:
        re.compile(regex, re.VERBOSE)
    except re.error as e:
        raise ValidationError('Invalid regex: %s' % e.message)


class NavigationBar(MPTTModel):
    class Meta:
        verbose_name = _('navigation item')
        verbose_name_plural = _('navigation bar')

    class MPTTMeta:
        order_insertion_by = ['order']

    order = models.PositiveIntegerField(db_index=True, verbose_name=_('order'))
    key = models.CharField(max_length=10, unique=True, verbose_name=_('identifier'))
    label = models.CharField(max_length=20, verbose_name=_('label'))
    path = models.CharField(max_length=255, verbose_name=_('link path'))
    regex = models.TextField(verbose_name=_('highlight regex'), validators=[validate_regex])
    parent = TreeForeignKey('self', verbose_name=_('parent item'), null=True, blank=True,
                            related_name='children', on_delete=models.CASCADE)

    def __str__(self):
        return self.label

    @property
    def pattern(self, cache={}):
        # A cache with a bad policy is an alias for memory leak
        # Thankfully, there will never be too many regexes to cache.
        if self.regex in cache:
            return cache[self.regex]
        else:
            pattern = cache[self.regex] = re.compile(self.regex, re.VERBOSE)
            return pattern


class BlogPost(models.Model):
    title = models.CharField(verbose_name=_('post title'), max_length=100)
    authors = models.ManyToManyField(Profile, verbose_name=_('authors'), blank=True)
    slug = models.SlugField(verbose_name=_('slug'))
    visible = models.BooleanField(verbose_name=_('public visibility'), default=False)
    sticky = models.BooleanField(verbose_name=_('sticky'), default=False)
    publish_on = models.DateTimeField(verbose_name=_('publish after'))
    content = models.TextField(verbose_name=_('post content'))
    summary = models.TextField(verbose_name=_('post summary'), blank=True)
    og_image = models.CharField(verbose_name=_('OpenGraph image'), default='', max_length=150, blank=True)
    score = models.IntegerField(verbose_name=_('votes'), default=0)
    global_post = models.BooleanField(verbose_name=_('global post'), default=False,
                                      help_text=_('Display this blog post at the homepage.'))
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name=_('organization'),
                                     related_name='post_author_org', blank=True, null=True, db_index=True)

    def __str__(self):
        return self.title

    def vote(self, delta):
        self.score += delta
        self.save(update_fields=['score'])

        # Only update contributions for global and personal posts
        if self.visible and self.organization is None:
            for author in self.authors.all():
                # Blog votes are counted as comment votes
                author.update_contribution_points(delta * settings.VNOJ_CP_COMMENT)

    def get_absolute_url(self):
        return reverse('blog_post', args=(self.id, self.slug))

    def can_see(self, user):
        # Post is public
        if self.visible and self.publish_on <= timezone.now():
            # Post is private to an organization
            if self.organization:
                if not user.is_authenticated:
                    return False
                if user.profile.organizations.filter(id=self.organization.pk).exists():
                    return True
                return self.is_editable_by(user)

            # Global or personal post should always be visible
            return True

        # Post is not public
        return self.is_editable_by(user)

    def is_editable_by(self, user):
        if not user.is_authenticated:
            return False
        if user.has_perm('judge.edit_all_post'):
            return True
        if self.organization:
            return self.organization.is_admin(user.profile) and \
                user.has_perm('judge.edit_organization_post') and \
                self.authors.filter(id=user.profile.id).exists()
        return self.authors.filter(id=user.profile.id).exists()

    class Meta:
        permissions = (
            ('edit_all_post', _('Edit all posts')),
            ('edit_organization_post', _('Edit organization posts')),
            ('mark_global_post', _('Mark post as global')),
            ('pin_post', _('Pin post')),
        )
        verbose_name = _('blog post')
        verbose_name_plural = _('blog posts')


class BlogVote(models.Model):
    voter = models.ForeignKey(Profile, related_name='voted_blogs', on_delete=CASCADE)
    blog = models.ForeignKey(BlogPost, related_name='votes', on_delete=CASCADE)
    score = models.IntegerField()

    class Meta:
        unique_together = ['voter', 'blog']
        verbose_name = _('blog vote')
        verbose_name_plural = _('blog votes')


def validate_short_code(code):
    """Validate short code format: only alphanumeric, dash, and underscore."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', code):
        raise ValidationError(_('Short code can only contain letters, numbers, dashes, and underscores'))

    # Reserved keywords that cannot be used
    reserved = [
        'admin', 'api', 'problem', 'problems', 'contest', 'contests',
        'user', 'users', 'post', 'posts', 'submission', 'submissions',
        'organization', 'organizations', 'shortener', 's', 'about',
        'status', 'runtimes', 'language', 'languages', 'judge', 'judges',
    ]
    if code.lower() in reserved:
        raise ValidationError(_('This short code is reserved by the system'))


class URLShortener(models.Model):
    # Core fields
    short_code = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        validators=[validate_short_code],
        verbose_name=_('short code'),
        help_text=_('Custom short URL identifier (max 30 characters, letters/numbers/dash/underscore only)'),
    )
    long_url = models.URLField(
        max_length=2000,
        verbose_name=_('destination URL'),
        help_text=_('The full URL to redirect to'),
    )

    # Ownership
    creator = models.ForeignKey(
        Profile,
        on_delete=CASCADE,
        related_name='shortened_urls',
        verbose_name=_('creator'),
    )
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='shortened_urls',
        verbose_name=_('organization'),
        help_text=_('Optional: Associate this URL with an organization'),
    )

    # Site support (for multi-site/subdomain)
    site = models.ForeignKey(
        Site,
        on_delete=CASCADE,
        default=settings.SITE_ID,
        verbose_name=_('site'),
        help_text=_('Site/domain where this short URL is active'),
    )

    # Metadata
    description = models.TextField(
        blank=True,
        verbose_name=_('description'),
        help_text=_('Optional description or notes about this URL'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))

    # Analytics
    click_count = models.IntegerField(
        default=0,
        verbose_name=_('click count'),
        help_text=_('Number of times this short URL has been accessed'),
    )
    last_accessed = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('last accessed'),
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('active'),
        help_text=_('Inactive URLs will return 404'),
    )

    class Meta:
        permissions = (
            ('create_url_shortener', _('Can create shortened URLs')),
            ('view_all_url_stats', _('Can view all URL statistics')),
        )
        verbose_name = _('URL shortener')
        verbose_name_plural = _('URL shorteners')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['short_code', 'site']),
            models.Index(fields=['creator', '-created_at']),
        ]

    def __str__(self):
        return f'{self.short_code} → {self.long_url[:50]}{"..." if len(self.long_url) > 50 else ""}'

    def get_absolute_url(self):
        return reverse('url_shortener_redirect', args=[self.short_code])

    def get_full_short_url(self):
        """Get the complete short URL including domain."""
        domain = self.site.domain
        path = self.get_absolute_url()
        return f'https://{domain}{path}'

    def increment_clicks(self):
        """Atomically increment click count and update last accessed time."""
        URLShortener.objects.filter(pk=self.pk).update(
            click_count=F('click_count') + 1,
            last_accessed=timezone.now(),
        )

    @staticmethod
    def generate_random_code(length=5, max_attempts=10):
        """
        Generate a random short code with smart uniqueness checking.

        Args:
            length: Length of the random code (default 5)
            max_attempts: Maximum number of attempts to find a unique code

        Returns:
            A unique random short code, or None if failed after max_attempts
        """
        chars = string.ascii_lowercase + string.digits

        for attempt in range(max_attempts):
            code = ''.join(random.choice(chars) for _ in range(length))

            # Fast uniqueness check using exists()
            if not URLShortener.objects.filter(short_code=code).exists():
                return code

        # If still can't find unique code after max_attempts, try with longer length
        if length < 10:
            return URLShortener.generate_random_code(length=length + 1, max_attempts=max_attempts)

        return None

    def can_edit(self, user):
        """Check if user can edit this URL shortener."""
        if not user.is_authenticated:
            return False

        # Creator can always edit
        if self.creator_id == user.profile.id:
            return True

        # Users with view_all_url_stats permission can edit all
        if user.has_perm('judge.view_all_url_stats'):
            return True

        return False
