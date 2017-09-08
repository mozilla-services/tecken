# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import logging
from urllib.parse import urlparse, urlunparse

from django import http
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission, User, Group
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.base.decorators import (
    api_login_required,
    api_permission_required,
    api_require_http_methods,
    api_require_POST,
    api_superuser_required,
)
from . import forms

logger = logging.getLogger('tecken')


def auth(request):
    context = {}
    if request.user.is_authenticated:
        context['user'] = {
            'email': request.user.email,
            'is_active': request.user.is_active,
            'is_superuser': request.user.is_superuser,
            'permissions': [],
        }
        permissions = Permission.objects.filter(codename__in=(
            'view_all_uploads',
            'upload_symbols',
            'manage_tokens',
        ))
        user_permissions = request.user.get_all_permissions()
        for permission in permissions.select_related('content_type'):
            codename = (
                f'{permission.content_type.app_label}.{permission.codename}'
            )
            if codename in user_permissions:
                context['user']['permissions'].append({
                    'id': permission.id,
                    'codename': codename,
                    'name': permission.name
                })

        # do we need to add the one for managing tokens?
        context['sign_out_url'] = request.build_absolute_uri(
            reverse('oidc_logout')
        )
    else:
        context['sign_in_url'] = request.build_absolute_uri(
            reverse('oidc_authentication_init')
        )
        context['user'] = None
    return http.JsonResponse(context)


@api_login_required
@api_permission_required('tokens.manage_tokens')
def tokens(request):

    def serialize_permissions(permissions):
        return [
            {
                'name': x.name,
                'id': x.id
            }
            for x in permissions
        ]

    all_permissions = (
        Permission.objects.get(codename='upload_symbols'),
        Permission.objects.get(codename='view_all_uploads'),
        Permission.objects.get(codename='manage_tokens'),
    )
    all_user_permissions = request.user.get_all_permissions()
    possible_permissions = [
        x for x in all_permissions
        if (
            f'{x.content_type}.{x.codename}' in all_user_permissions or
            request.user.is_superuser
        )
    ]

    if request.method == 'POST':
        form = forms.TokenForm(request.POST)
        if form.is_valid():
            # Check that none of the sent permissions isn't possible
            for permission in form.cleaned_data['permissions']:
                if permission not in possible_permissions:
                    return http.JsonResponse({
                        'errors': {
                            'permissions': (
                                f'{permission.name} not a valid permission'
                            ),
                        },
                    }, status=403)
            expires_at = timezone.now() + datetime.timedelta(
                days=form.cleaned_data['expires']
            )
            token = Token.objects.create(
                user=request.user,
                expires_at=expires_at,
                notes=form.cleaned_data['notes'].strip(),
            )
            for permission in form.cleaned_data['permissions']:
                token.permissions.add(permission)

            return http.JsonResponse({'ok': True}, status=201)
        else:
            return http.JsonResponse({'errors': form.errors}, status=400)

    form = forms.TokensForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    filter_state = form.cleaned_data['state']

    context = {
        'tokens': [],
        'permissions': serialize_permissions(possible_permissions),
    }
    qs = Token.objects.filter(user=request.user)
    # Before we filter the queryset further, use it to calculate counts.
    context['totals'] = {
        'all': qs.count(),
        'active': qs.filter(expires_at__gt=timezone.now()).count(),
        'expired': qs.filter(expires_at__lte=timezone.now()).count(),
    }
    if filter_state == 'all':
        pass
    elif filter_state == 'expired':
        qs = qs.filter(expires_at__lte=timezone.now())
    else:
        # The default is to only return active ones
        qs = qs.filter(expires_at__gt=timezone.now())

    for token in qs.order_by('-created_at'):
        context['tokens'].append({
            'id': token.id,
            'expires_at': token.expires_at,
            'is_expired': token.is_expired,
            'key': token.key,
            'permissions': serialize_permissions(token.permissions.all()),
            'notes': token.notes,
            'created_at': token.created_at,
        })

    return http.JsonResponse(context)


@api_require_http_methods(['DELETE'])
@api_login_required
def delete_token(request, id):
    if request.user.is_superuser:
        token = get_object_or_404(Token, id=id)
    else:
        token = get_object_or_404(Token, id=id, user=request.user)
    token.delete()

    return http.JsonResponse({'ok': True})


def _serialize_permission(p):
    return {
        'id': p.id,
        'name': p.name,
    }


def _serialize_group(group):
    return {
        'id': group.id,
        'name': group.name,
        'permissions': [
            _serialize_permission(x) for x in group.permissions.all()
        ],
    }


@api_login_required
@api_permission_required('users.change_user')
def users(request):
    context = {
        'users': [],
    }

    # A cache. If two users belong to the same group, we don't want to
    # have to figure out that group's permissions more than once.
    all_group_permissions = {}

    def groups_to_permissions(groups):
        all_permissions = []
        permission_ids = set()
        for group in groups:
            if group.id not in all_group_permissions:
                # populate the cache for this group
                all_group_permissions[group.id] = []
                for perm in group.permissions.all():
                    all_group_permissions[group.id].append(
                        _serialize_permission(perm)
                    )
            for permission in all_group_permissions[group.id]:
                if permission['id'] in permission_ids:
                    continue
                permission_ids.add(permission['id'])
                all_permissions.append(permission)
        return sorted(all_permissions, key=lambda x: x['name'])

    # Make a map of user_id to count of Token objects
    tokens_count = {}
    for rec in Token.objects.values('user').annotate(count=Count('user')):
        tokens_count[rec['user']] = rec['count']
    uploads_count = {}
    for rec in Upload.objects.values('user').annotate(count=Count('user')):
        uploads_count[rec['user']] = rec['count']

    qs = User.objects.all()
    for user in qs.order_by('-last_login'):
        context['users'].append({
            'id': user.id,
            'email': user.email,
            'last_login': user.last_login,
            'date_joined': user.date_joined,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'no_uploads': uploads_count.get(user.id, 0),
            'no_tokens': tokens_count.get(user.id, 0),
            'groups': [
                _serialize_group(x) for x in user.groups.all()
            ],
            'permissions': groups_to_permissions(user.groups.all()),
        })

    return http.JsonResponse(context)


@csrf_protect
@api_login_required
@api_permission_required('users.change_user')
def edit_user(request, id):
    user = get_object_or_404(User, id=id)

    if request.method == 'POST':
        form = forms.UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            # Remove all the groups that user might have been in before
            groups = form.cleaned_data['groups']
            for group in set(user.groups.all()) - set(groups):
                user.groups.remove(group)
            for group in set(groups) - set(user.groups.all()):
                user.groups.add(group)
            return http.JsonResponse({'ok': True}, status=200)
        else:
            return http.JsonResponse({'errors': form.errors}, status=400)

    context = {}
    context['user'] = {
        'id': user.id,
        'is_active': user.is_active,
        'is_superuser': user.is_superuser,
        'email': user.email,
        'groups': [
            _serialize_group(x) for x in user.groups.all()
        ],
    }
    context['groups'] = [
        _serialize_group(x) for x in Group.objects.all()
    ]
    # print([x for x in dir(request) if x])
    # print([x for x in dir(request) if 'csrf' in x])
    from django.middleware.csrf import get_token
    context['csrf_token'] = get_token(request)
    return http.JsonResponse(context)


@api_login_required
def uploads(request):
    context = {
        'uploads': [],
        'can_view_all': request.user.has_perm('upload.view_all_uploads'),
    }

    form = forms.UploadsForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse(
            {'errors': pagination_form.errors},
            status=400
        )

    qs = Upload.objects.all()
    # Force the filtering to *your* symbols unless you have the
    # 'view_all_uploads' permission.
    if context['can_view_all']:
        if form.cleaned_data['user']:
            operator, user = form.cleaned_data['user']
            if operator == '!':
                qs = qs.exclude(user=user)
            else:
                qs = qs.filter(user=user)
    else:
        qs = qs.filter(user=request.user)
    orm_operators = {
        '<=': 'lte',
        '>=': 'gte',
        '=': 'exact',
        '<': 'lt',
        '>': 'gt',
    }
    for operator, value in form.cleaned_data['size']:
        orm_operator = 'size__{}'.format(
            orm_operators[operator]
        )
        qs = qs.filter(**{orm_operator: value})
    for key in ('created_at', 'completed_at'):
        for operator, value in form.cleaned_data.get(key, []):
            if value == 'cancelled':
                qs = qs.filter(cancelled_at__isnull=False)
            elif value is None:
                orm_operator = f'{key}__isnull'
                qs = qs.filter(**{orm_operator: True})
            elif operator == '=' and value.hour == 0 and value.minute == 0:
                # When querying on a specific day, make it a little easier
                qs = qs.filter(**{
                    f'{key}__gte': value,
                    f'{key}__lt': value + datetime.timedelta(days=1),
                })
            else:
                orm_operator = '{}__{}'.format(
                    key,
                    orm_operators[operator]
                )
                qs = qs.filter(**{orm_operator: value})

    qs = qs.select_related('user')

    batch_size = settings.API_UPLOADS_BATCH_SIZE

    page = pagination_form.cleaned_data['page']
    start = (page - 1) * batch_size
    end = start + batch_size

    rows = []
    for upload in qs.order_by('-created_at')[start:end]:
        rows.append({
            'id': upload.id,
            'user': {
                'email': upload.user.email,
            },
            'filename': upload.filename,
            'size': upload.size,
            'bucket_name': upload.bucket_name,
            'bucket_region': upload.bucket_region,
            'bucket_endpoint_url': upload.bucket_endpoint_url,
            'inbox_key': upload.inbox_key,
            'skipped_keys': upload.skipped_keys or [],
            'ignored_keys': upload.ignored_keys or [],
            'download_url': upload.download_url,
            'completed_at': upload.completed_at,
            'created_at': upload.created_at,
            'attempts': upload.attempts,
            'cancelled_at': upload.cancelled_at,
            'cancellable': _is_cancellable(upload),
        })
    # Make a FileUpload aggregate count on these uploads
    file_upload_counts = FileUpload.objects.filter(
        upload_id__in=[x['id'] for x in rows]
    ).values('upload').annotate(count=Count('upload'))
    # Convert it to a dict
    file_upload_counts_map = {
        x['upload']: x['count'] for x in file_upload_counts
    }
    for upload in rows:
        upload['files_count'] = file_upload_counts_map.get(upload['id'], 0)

    context['uploads'] = rows
    context['total'] = qs.count()
    context['batch_size'] = batch_size

    return http.JsonResponse(context)


def _is_cancellable(upload_obj):
    return (
        not upload_obj.cancelled_at and
        not upload_obj.completed_at and
        upload_obj.attempts < settings.UPLOAD_REATTEMPT_LIMIT_TIMES
    )


@api_login_required
def upload(request, id):
    obj = get_object_or_404(Upload, id=id)
    # You're only allowed to see this if it's yours or you have the
    # 'view_all_uploads' permission.
    if not (
        obj.user == request.user or
        request.user.has_perm('upload.view_all_uploads')
    ):
        return http.JsonResponse({
            'error': 'Insufficient access to view this upload'
        }, status=403)

    upload_dict = {
        'id': obj.id,
        'filename': obj.filename,
        'user': {
            'id': obj.user.id,
            'email': obj.user.email,
        },
        'size': obj.size,
        'bucket_name': obj.bucket_name,
        'bucket_region': obj.bucket_region,
        'bucket_endpoint_url': obj.bucket_endpoint_url,
        'inbox_key': obj.inbox_key,
        'skipped_keys': obj.skipped_keys or [],
        'ignored_keys': obj.ignored_keys or [],
        'download_url': obj.download_url,
        'completed_at': obj.completed_at,
        'created_at': obj.created_at,
        'attempts': obj.attempts,
        'file_uploads': [],
        'cancelled_at': obj.cancelled_at,
        'cancellable': _is_cancellable(obj),
    }
    file_uploads_qs = FileUpload.objects.filter(upload=obj)
    for file_upload in file_uploads_qs.order_by('created_at'):
        upload_dict['file_uploads'].append({
            'id': file_upload.id,
            'bucket_name': file_upload.bucket_name,
            'key': file_upload.key,
            'update': file_upload.update,
            'compressed': file_upload.compressed,
            'size': file_upload.size,
            'microsoft_download': file_upload.microsoft_download,
            'completed_at': file_upload.completed_at,
            'created_at': file_upload.created_at,
        })
    context = {
        'upload': upload_dict,
    }
    return http.JsonResponse(context)


@api_login_required
@api_require_POST
def cancel_upload(request, id):
    obj = get_object_or_404(Upload, id=id)
    # You're only allowed to see this if it's yours or you have the
    # 'view_all_uploads' permission.
    if not (
        obj.user == request.user or
        request.user.has_perm('upload.view_all_uploads')
    ):
        return http.JsonResponse({
            'error': 'Insufficient access to view this upload'
        }, status=403)

    obj.cancelled_at = timezone.now()
    obj.save()
    return http.JsonResponse({'ok': True})


@api_login_required
@api_permission_required('upload.view_all_uploads')
def upload_files(request):
    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse(
            {'errors': pagination_form.errors},
            status=400
        )
    page = pagination_form.cleaned_data['page']

    form = forms.FileUploadsForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    qs = FileUpload.objects.all()
    orm_operators = {
        '<=': 'lte',
        '>=': 'gte',
        '=': 'exact',
        '<': 'lt',
        '>': 'gt',
    }
    for operator, value in form.cleaned_data['size']:
        orm_operator = 'size__{}'.format(
            orm_operators[operator]
        )
        qs = qs.filter(**{orm_operator: value})
    for key in ('created_at', 'completed_at'):
        for operator, value in form.cleaned_data.get(key, []):
            if value is None:
                orm_operator = f'{key}__isnull'
                qs = qs.filter(**{orm_operator: True})
            elif operator == '=' and value.hour == 0 and value.minute == 0:
                # When querying on a specific day, make it a little easier
                qs = qs.filter(**{
                    f'{key}__gte': value,
                    f'{key}__lt': value + datetime.timedelta(days=1),
                })
            else:
                orm_operator = '{}__{}'.format(
                    key,
                    orm_operators[operator]
                )
                qs = qs.filter(**{orm_operator: value})
    if form.cleaned_data.get('key'):
        key_q = Q(key__icontains=form.cleaned_data['key'][0])
        for other in form.cleaned_data['key'][1:]:
            key_q &= Q(key__icontains=other)
        qs = qs.filter(key_q)
    if form.cleaned_data['download']:
        if form.cleaned_data['download'] == 'microsoft':
            qs = qs.filter(microsoft_download=True)
    if form.cleaned_data.get('bucket_name'):
        qs = qs.filter(bucket_name__in=form.cleaned_data.get('bucket_name'))

    files = []
    batch_size = settings.API_FILES_BATCH_SIZE
    start = (page - 1) * batch_size
    end = start + batch_size

    upload_ids = set()
    for file_upload in qs.order_by('-created_at')[start:end]:
        files.append({
            'id': file_upload.id,
            'key': file_upload.key,
            'update': file_upload.update,
            'compressed': file_upload.compressed,
            'microsoft_download': file_upload.microsoft_download,
            'size': file_upload.size,
            'bucket_name': file_upload.bucket_name,
            'completed_at': file_upload.completed_at,
            'created_at': file_upload.created_at,
            'upload': file_upload.upload_id,
        })
        if file_upload.upload_id:
            upload_ids.add(file_upload.upload_id)

    uploads = {
        x.id: x
        for x in Upload.objects.filter(
            id__in=upload_ids
        ).select_related('user')
    }

    uploads_cache = {}

    def hydrate_upload(upload_id):
        if upload_id:
            if upload_id not in uploads_cache:
                upload = uploads[upload_id]
                uploads_cache[upload_id] = {
                    'id': upload.id,
                    'user': {
                        'id': upload.user.id,
                        'email': upload.user.email,
                    },
                    'created_at': upload.created_at,
                }
            return uploads_cache[upload_id]

    for file_upload in files:
        file_upload['upload'] = hydrate_upload(file_upload['upload'])

    total = qs.count()
    context = {
        'files': files,
        'total': total,
        'batch_size': batch_size,
    }

    return http.JsonResponse(context)


@api_login_required
def stats(request):
    # XXX Perhaps we should have some stats coming from Redis about the
    # state of the LRU cache.

    numbers = {}

    all_uploads = request.user.has_perm('upload.can_view_all')
    upload_qs = Upload.objects.all()
    if not all_uploads:
        upload_qs = upload_qs.filter(user=request.user)

    # Gather some numbers about uploads
    def count_and_size(start, end):
        qs = upload_qs.filter(created_at__gte=start, created_at__lt=end)
        return {
            'count': qs.count(),
            'total_size': qs.aggregate(size=Sum('size'))['size'],
        }

    today = timezone.now()
    start_today = today.replace(hour=0, minute=0, second=0)
    uploads_today = count_and_size(start_today, today)
    start_yesterday = start_today - datetime.timedelta(days=1)
    uploads_yesterday = count_and_size(start_yesterday, start_today)
    start_this_month = today.replace(day=1)
    uploads_this_month = count_and_size(start_this_month, today)
    start_this_year = start_this_month.replace(month=1)
    uploads_this_year = count_and_size(start_this_year, today)
    numbers['uploads'] = {
        'all_uploads': all_uploads,
        'today': uploads_today,
        'yesterday': uploads_yesterday,
        'this_month': uploads_this_month,
        'this_year': uploads_this_year,
    }

    # Gather some numbers about tokens
    tokens_qs = Token.objects.filter(user=request.user)
    numbers['tokens'] = {
        'total': tokens_qs.count(),
        'expired': tokens_qs.filter(expires_at__lt=today).count(),
    }

    # Gather some numbers about users
    if request.user.is_superuser:
        users_qs = User.objects.all()
        numbers['users'] = {
            'total': users_qs.count(),
            'superusers': users_qs.filter(is_superuser=True).count(),
            'active': users_qs.filter(is_active=True).count(),
            'not_active': users_qs.filter(is_active=False).count(),
        }

    context = {
        'stats': numbers,
    }
    return http.JsonResponse(context)


@api_login_required
@api_superuser_required
def current_settings(request):
    """return a JSON dict of a selection of settings to describe the
    current system. These are only accessible to superusers and the settings
    it includes is whitelisted and manually maintained here in this view.
    """
    context = {
        'settings': []
    }

    def clean_url(value):
        parsed = urlparse(value)
        if '@' in parsed.netloc:
            # There might be a password in the netloc part.
            # It's extremely unlikely but just in case we ever forget
            # make sure it's never "exposed".
            parts = list(parsed)
            parts[1] = 'user:xxxxxx@' + parts[1].split('@', 1)[1]
            return urlunparse(parts)
        return value

    # Only include keys that can never be useful in security context.
    keys = (
        'ENABLE_AUTH0_BLOCKED_CHECK',
        'ENABLE_TOKENS_AUTHENTICATION',
        'ENABLE_DOWNLOAD_FROM_MICROSOFT',
        'ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS',
        'DOWNLOAD_FILE_EXTENSIONS_WHITELIST',
    )
    for key in keys:
        value = getattr(settings, key)
        context['settings'].append({
            'key': key,
            'value': value,
        })

    # Now for some oddballs
    context['settings'].append({
        'key': 'UPLOAD_DEFAULT_URL',
        'value': clean_url(settings.UPLOAD_DEFAULT_URL)
    })
    context['settings'].append({
        'key': 'SYMBOL_URLS',
        'value': json.dumps([clean_url(x) for x in settings.SYMBOL_URLS])
    })
    context['settings'].append({
        'key': 'UPLOAD_URL_EXCEPTIONS',
        'value': json.dumps({
            k: clean_url(v) for k, v in settings.UPLOAD_URL_EXCEPTIONS.items()
        })
    })
    context['settings'].sort(key=lambda x: x['key'])
    return http.JsonResponse(context)
