import json
import logging
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger('judge.tus')
User = get_user_model()
SessionStore = import_module(settings.SESSION_ENGINE).SessionStore

_HOOK_PRE_CREATE = 'pre-create'


def _can_upload(user) -> bool:
    return user is not None and user.is_authenticated and user.is_active


def _resolve_user_from_request(request):
    session_cookie_name = settings.SESSION_COOKIE_NAME
    session_key = request.COOKIES.get(session_cookie_name)

    if not session_key:
        return None

    session = SessionStore(session_key=session_key)
    user_id = session.get('_auth_user_id')

    if not user_id:
        return None

    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


def _handle_pre_create(request) -> HttpResponse:
    session_cookie_name = settings.SESSION_COOKIE_NAME
    session_key = request.COOKIES.get(session_cookie_name)
    
    # LOG RA ĐỂ ĐIỀU TRA
    logger.debug('tus-hook: Raw cookie sessionid=%s', session_key)
    
    user = _resolve_user_from_request(request)
    
    if user is None:
        logger.warning('tus-hook: User could not be resolved! Check if sessionid is valid.')
    
    if not _can_upload(user):
        logger.warning('tus-hook: pre-create rejected. User=%s', user)
        return HttpResponse(status=403)
    
    logger.debug('tus-hook: pre-create approved for user=%s', user.username)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def tus_hook(request):
    hook_name = request.META.get('HTTP_HOOK_NAME', '')

    if hook_name == _HOOK_PRE_CREATE:
        return _handle_pre_create(request)

    try:
        payload = json.loads(request.body)
        logger.debug('tus-hook: hook=%s upload_id=%s', hook_name, payload.get('Upload', {}).get('ID', ''))
    except (json.JSONDecodeError, AttributeError):
        logger.debug('tus-hook: hook=%s (unparseable body)', hook_name)

    return HttpResponse(status=200)
