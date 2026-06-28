import json
import logging
import os
import re
import shutil
import uuid
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger('judge.tus')

_UPLOAD_ID_RE = re.compile(r'^[a-f0-9]{32}$')


def resolve_tus_upload(upload_id, problem_code, user_id):
    """Move a completed TUS upload into SUBMISSION_FILE_UPLOAD_MEDIA_DIR.

    Returns the URL path of the stored file (same format as submission_uploader).
    Raises ValueError on invalid/missing upload.
    """
    if not _UPLOAD_ID_RE.match(upload_id):
        raise ValueError(f'Invalid TUS upload ID: {upload_id}')

    tusd_dir = default_storage.path(settings.TUSD_DATA_DIR)
    data_path = os.path.join(tusd_dir, upload_id)
    info_path = data_path + '.info'

    if not os.path.isfile(data_path):
        raise ValueError(f'TUS upload not found: {upload_id}')

    # Read .info to get original filename + extension
    ext = ''
    if os.path.isfile(info_path):
        try:
            with open(info_path) as f:
                info = json.load(f)
            original_name = info.get('MetaData', {}).get('filename', '')
            if '.' in original_name:
                ext = os.path.splitext(original_name)[1]
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning('Failed to parse .info file for TUS upload %s: %s', upload_id, e)

    # Build destination path
    dest_name = str(uuid.uuid4()) + ext
    rel_path = os.path.join(
        settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR,
        problem_code, str(user_id), dest_name,
    )
    abs_dest = default_storage.path(rel_path)
    os.makedirs(os.path.dirname(abs_dest), exist_ok=True)

    # Move (not copy)
    shutil.move(data_path, abs_dest)

    # Cleanup .info
    if os.path.isfile(info_path):
        try:
            os.remove(info_path)
        except OSError as e:
            logger.warning('Failed to delete .info file %s: %s', info_path, e)

    logger.info('TUS upload %s moved to %s', upload_id, rel_path)

    # Build URL (same pattern as submission_uploader)
    url_base = getattr(
        settings, 'SUBMISSION_FILE_UPLOAD_URL_PREFIX',
        urljoin(settings.MEDIA_URL, settings.SUBMISSION_FILE_UPLOAD_MEDIA_DIR),
    )
    if not url_base.endswith('/'):
        url_base += '/'
    return urljoin(url_base, os.path.join(problem_code, str(user_id), dest_name))


def get_tus_upload_file(upload_id):
    """Retrieve a completed TUS upload wrapped as a Django File object.

    The returned File object is opened in binary mode, and has custom
    attributes pointing to the temporary paths so it can be cleaned up later.
    """
    if not _UPLOAD_ID_RE.match(upload_id):
        raise ValueError(f'Invalid TUS upload ID: {upload_id}')

    tusd_dir = default_storage.path(settings.TUSD_DATA_DIR)
    data_path = os.path.join(tusd_dir, upload_id)
    info_path = data_path + '.info'

    if not os.path.isfile(data_path):
        raise ValueError(f'TUS upload not found: {upload_id}')

    # Read original filename from .info if available
    filename = upload_id + '.zip'
    if os.path.isfile(info_path):
        try:
            with open(info_path) as f:
                info = json.load(f)
            original_name = info.get('MetaData', {}).get('filename', '')
            if original_name:
                filename = original_name
        except Exception as e:
            logger.warning('Failed to retrieve original filename for TUS upload %s: %s', upload_id, e)

    from django.core.files import File
    f = open(data_path, 'rb')
    django_file = File(f, name=filename)
    django_file._tus_data_path = data_path
    django_file._tus_info_path = info_path
    return django_file
