from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from judge.forms import URLShortenerForm
from judge.models import URLShortener
from judge.utils.diggpaginator import DiggPaginator
from judge.utils.views import TitleMixin


class URLShortenerListView(LoginRequiredMixin, TitleMixin, ListView):
    """List all URL shorteners created by the current user or all if has permission."""
    model = URLShortener
    template_name = 'url_shortener/list.html'
    title = _('Manage URL Shorteners')
    context_object_name = 'shorteners'
    paginate_by = 50
    paginator_class = DiggPaginator

    def get_queryset(self):
        qs = URLShortener.objects.select_related('creator__user', 'organization', 'site')

        # Filter by current site
        current_site = get_current_site(self.request)
        qs = qs.filter(site=current_site)

        # If user has view_all_url_stats permission, show all
        if self.request.user.has_perm('judge.view_all_url_stats'):
            return qs.order_by('-created_at')

        # Otherwise, only show URLs created by this user
        return qs.filter(creator=self.request.profile).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_create'] = self.request.user.has_perm('judge.create_url_shortener')
        context['can_view_all'] = self.request.user.has_perm('judge.view_all_url_stats')
        return context


class URLShortenerCreateView(LoginRequiredMixin, PermissionRequiredMixin, TitleMixin, CreateView):
    """Create a new URL shortener."""
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'url_shortener/create.html'
    title = _('Create Short URL')
    permission_required = 'judge.create_url_shortener'
    success_url = reverse_lazy('url_shortener_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = get_current_site(self.request)
        return context

    def form_valid(self, form):
        # Set creator to current user
        form.instance.creator = self.request.profile

        # Set site to current site
        form.instance.site = get_current_site(self.request)

        return super().form_valid(form)


class URLShortenerUpdateView(LoginRequiredMixin, TitleMixin, UpdateView):
    """Edit an existing URL shortener."""
    model = URLShortener
    form_class = URLShortenerForm
    template_name = 'url_shortener/edit.html'
    title = _('Edit Short URL')
    slug_field = 'short_code'
    slug_url_kwarg = 'code'
    success_url = reverse_lazy('url_shortener_list')

    def get_queryset(self):
        # Filter by current site
        current_site = get_current_site(self.request)
        return URLShortener.objects.filter(site=current_site)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)

        # Check if user can edit this URL
        if not obj.can_edit(self.request.user):
            raise Http404()

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = get_current_site(self.request)
        context['is_edit'] = True
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Remove auto_generate field in edit mode
        if 'auto_generate' in form.fields:
            del form.fields['auto_generate']
        # Make short_code required in edit mode
        form.fields['short_code'].required = True
        return form


class URLShortenerDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a URL shortener."""
    model = URLShortener
    template_name = 'url_shortener/delete.html'
    slug_field = 'short_code'
    slug_url_kwarg = 'code'
    success_url = reverse_lazy('url_shortener_list')

    def get_queryset(self):
        # Filter by current site
        current_site = get_current_site(self.request)
        return URLShortener.objects.filter(site=current_site)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)

        # Check if user can delete this URL
        if not obj.can_edit(self.request.user):
            raise Http404()

        return obj


def url_shortener_redirect(request, code):
    """
    Public redirect view - redirects to the long URL and tracks clicks.
    """
    # Get current site
    current_site = get_current_site(request)

    # Get the shortener object
    shortener = get_object_or_404(
        URLShortener,
        short_code=code,
        site=current_site,
        is_active=True,
    )

    # Increment click count
    shortener.increment_clicks()

    # Redirect to the long URL
    return redirect(shortener.long_url)
