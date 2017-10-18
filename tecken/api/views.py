# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import logging
from urllib.parse import urlparse, urlunparse

from dockerflow.version import get_version as dockerflow_get_version
from django_redis import get_redis_connection

from django import http
from django import get_version
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission, User, Group
from django.db.models import Count, Q, Sum, Avg, F
from django.db.models import Aggregate
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect
from django.db import connection

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.base.decorators import (
    api_login_required,
    api_permission_required,
    api_require_http_methods,
    api_superuser_required,
)
from . import forms

logger = logging.getLogger('tecken')


class SumCardinality(Aggregate):
    template = 'SUM(CARDINALITY(%(expressions)s))'


ORM_OPERATORS = {
    '<=': 'lte',
    '>=': 'gte',
    '=': 'exact',
    '<': 'lt',
    '>': 'gt',
}


def _filter_form_dates(qs, form, keys):
    for key in keys:
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
                if operator == '>':
                    # Because we use microseconds in the ORM, but when
                    # datetimes are passed back end forth in XHR, the
                    # datetimes are converted with isoformat() which
                    # drops microseconds. Therefore add 1 second to
                    # avoid matching the latest date.
                    value += datetime.timedelta(seconds=1)
                orm_operator = '{}__{}'.format(
                    key,
                    ORM_OPERATORS[operator]
                )
                qs = qs.filter(**{orm_operator: value})
    return qs


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
    qs = filter_uploads(qs, context['can_view_all'], request.user, form)

    batch_size = settings.API_UPLOADS_BATCH_SIZE

    page = pagination_form.cleaned_data['page']
    start = (page - 1) * batch_size
    end = start + batch_size

    aggregates_numbers = qs.aggregate(
        count=Count('id'),
        size_avg=Avg('size'),
        size_sum=Sum('size'),
        skipped_sum=SumCardinality('skipped_keys'),
    )
    context['aggregates'] = {
        'uploads': {
            'count': aggregates_numbers['count'],
            'size': {
                'average': aggregates_numbers['size_avg'],
                'sum': aggregates_numbers['size_sum'],
            },
            'skipped': {
                'sum': aggregates_numbers['skipped_sum'],
            },
        },
    }
    file_uploads_qs = FileUpload.objects.filter(upload__in=qs)
    context['aggregates']['files'] = {
        'count': file_uploads_qs.count(),
    }

    # Prepare a map of all user_id => user attributes
    # This assumes that there are relatively few users who upload.
    distinct_users_ids = [
        x['user_id'] for x in
        qs.values('user_id').distinct('user_id')
    ]
    if distinct_users_ids:
        # Only bother if there is a any distinct users
        user_map = {
            user.id: {'email': user.email}
            for user in User.objects.filter(id__in=distinct_users_ids)
        }
    rows = []
    for upload in qs.order_by('-created_at')[start:end]:
        rows.append({
            'id': upload.id,
            'user': user_map[upload.user_id],
            'filename': upload.filename,
            'size': upload.size,
            'bucket_name': upload.bucket_name,
            'bucket_region': upload.bucket_region,
            'bucket_endpoint_url': upload.bucket_endpoint_url,
            'skipped_keys': upload.skipped_keys or [],
            'ignored_keys': upload.ignored_keys or [],
            'download_url': upload.download_url,
            'completed_at': upload.completed_at,
            'created_at': upload.created_at,
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
    context['total'] = context['aggregates']['uploads']['count']
    context['batch_size'] = batch_size

    return http.JsonResponse(context)


def filter_uploads(qs, can_view_all, user, form):
    # Force the filtering to *your* symbols unless you have the
    # 'view_all_uploads' permission.
    if can_view_all:
        if form.cleaned_data['user']:
            operator, user = form.cleaned_data['user']
            if operator == '!':
                qs = qs.exclude(user=user)
            else:
                qs = qs.filter(user=user)
    else:
        qs = qs.filter(user=user)
    for operator, value in form.cleaned_data['size']:
        orm_operator = 'size__{}'.format(
            ORM_OPERATORS[operator]
        )
        qs = qs.filter(**{orm_operator: value})
    qs = _filter_form_dates(qs, form, ('created_at', 'completed_at'))
    return qs


@api_login_required
def uploads_datasets(request):
    can_view_all = request.user.has_perm('upload.view_all_uploads')

    form = forms.UploadsForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    qs = Upload.objects.all()
    qs = filter_uploads(qs, can_view_all, request.user, form)

    limit = int(request.GET.get('limit', 20))
    datasets = []
    # A dataset for all upload sizes
    datasets.append(_upload_sizes_dataset(qs, limit))
    # A dataset for all upload times
    datasets.append(_upload_times_dataset(qs, limit))
    # Counts of files, skipped per upload
    datasets.append(_upload_counts_dataset(qs, limit))

    context = {
        'datasets': datasets,
    }
    return http.JsonResponse(context)


def _upload_sizes_dataset(qs, limit):
    data = []
    data_upload_sizes = []
    data_file_sizes = []
    labels = []
    for upload in qs.order_by('-created_at')[:limit]:
        labels.append(upload.created_at.strftime('%d/%b'))
        data_upload_sizes.append(upload.size)
        files = FileUpload.objects.filter(upload=upload).aggregate(
            sum_size=Sum('size')
        )
        data_file_sizes.append(files['sum_size'] or 0)
    labels.reverse()
    data_upload_sizes.reverse()
    data_file_sizes.reverse()
    data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Uploads Received',
                'data': data_upload_sizes,
                'backgroundColor': 'rgba(255, 99, 132, 0.5)',
            },
            {
                'label': 'Files Uploaded',
                'data': data_file_sizes,
                'backgroundColor': 'rgba(54, 162, 235, 0.5)',
            },
        ]
    }
    return {
        'id': 'upload-sizes',
        'data': data,
        'type': 'bar',
        'value_type': 'bytes',
        'options': {
            'title': {
                'display': True,
                'text': (
                    f'Upload Sizes Compared to Files Uploaded (last {limit})'
                ),
            },
            'tooltips': {
                'mode': 'index',
                'intersect': False
            },
            'responsive': True,
            'scales': {
                'xAxes': [{
                    'display': False,
                }],
                'yAxes': [{
                    'display': True,
                }]
            }
        },
    }


def _upload_times_dataset(qs, limit):
    data = []
    data_upload_times = []
    data_file_times = []
    labels = []
    qs = qs.filter(completed_at__isnull=False)
    for upload in qs.order_by('-created_at')[:limit]:
        labels.append(upload.created_at.strftime('%d/%b'))
        diff = upload.completed_at - upload.created_at
        data_upload_times.append(diff.total_seconds())
        diffs = FileUpload.objects.filter(
            upload=upload,
            completed_at__isnull=False,
        ).aggregate(
            diff=Sum(F('completed_at') - F('created_at')),
        )['diff']
        data_file_times.append(diffs and diffs.total_seconds() or 0.0)
    labels.reverse()
    data_upload_times.reverse()
    data_file_times.reverse()
    data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Uploads Received',
                'data': data_upload_times,
                'backgroundColor': 'rgba(255, 99, 132, 0.5)',
            },
            {
                'label': 'Files Uploaded',
                'data': data_file_times,
                'backgroundColor': 'rgba(54, 162, 235, 0.5)',
            },
        ]
    }
    return {
        'id': 'upload-times',
        'value_type': 'seconds',
        'data': data,
        'type': 'bar',
        'options': {
            'title': {
                'display': True,
                'text': (
                    f'Upload Processing Times Compared to Files '
                    f'Uploaded (last {limit})'
                ),
            },
            'tooltips': {
                'mode': 'index',
                'intersect': False
            },
            'responsive': True,
            'scales': {
                'xAxes': [{
                    'display': False,
                }],
                'yAxes': [{
                    'display': True,
                }]
            }
        },
    }


def _upload_counts_dataset(qs, limit):
    data = []
    data_file_counts = []
    data_skipped_counts = []
    labels = []
    qs = qs.filter(completed_at__isnull=False)
    for upload in qs.order_by('-created_at')[:limit]:
        labels.append(upload.created_at.strftime('%d/%b'))

        files = FileUpload.objects.filter(
            upload=upload,
            completed_at__isnull=False,
        )
        data_file_counts.append(files.count())
        data_skipped_counts.append(
            upload.skipped_keys and len(upload.skipped_keys) or 0
        )
    labels.reverse()
    data_file_counts.reverse()
    data_skipped_counts.reverse()
    data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Files Uploaded',
                'data': data_file_counts,
                'backgroundColor': 'rgba(255, 99, 132, 0.5)',
            },
            {
                'label': 'Files Skipped',
                'data': data_skipped_counts,
                'backgroundColor': 'rgba(54, 162, 235, 0.5)',
            },
        ]
    }
    return {
        'id': 'upload-file-counts',
        'value_type': 'count',
        'data': data,
        'type': 'bar',
        'options': {
            'title': {
                'display': True,
                'text': (
                    f'Files Uploaded and Files Skipped (last {limit})'
                ),
            },
            'tooltips': {
                'mode': 'index',
                'intersect': False
            },
            'responsive': True,
            'scales': {
                'xAxes': [{
                    'display': False,
                }],
                'yAxes': [{
                    'display': True,
                }]
            }
        },
    }


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

    def make_upload_dict(upload_obj):
        file_uploads_qs = FileUpload.objects.filter(upload=upload_obj)
        file_uploads = []
        for file_upload in file_uploads_qs.order_by('created_at'):
            file_uploads.append({
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
        return {
            'id': upload_obj.id,
            'filename': upload_obj.filename,
            'user': {
                'id': upload_obj.user.id,
                'email': upload_obj.user.email,
            },
            'size': upload_obj.size,
            'bucket_name': upload_obj.bucket_name,
            'bucket_region': upload_obj.bucket_region,
            'bucket_endpoint_url': upload_obj.bucket_endpoint_url,
            'skipped_keys': upload_obj.skipped_keys or [],
            'ignored_keys': upload_obj.ignored_keys or [],
            'download_url': upload_obj.download_url,
            'completed_at': upload_obj.completed_at,
            'created_at': upload_obj.created_at,
            'file_uploads': file_uploads,
        }
    upload_dict = make_upload_dict(obj)

    related_qs = Upload.objects.exclude(id=obj.id).filter(
        size=obj.size,
        user=obj.user,
    )
    if obj.content_hash:
        related_qs = related_qs.filter(
            content_hash=obj.content_hash,
        )
    else:
        # The `content_hash` attribute is a new field as of Oct 10 2017.
        # So if the upload doesn't have that, use the filename which is
        # less than ideal.
        related_qs = related_qs.filter(
            filename=obj.filename
        )
    upload_dict['related'] = []
    for related_upload in related_qs.order_by('-created_at'):
        upload_dict['related'].append(make_upload_dict(related_upload))

    context = {
        'upload': upload_dict,
    }
    return http.JsonResponse(context)


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
    for operator, value in form.cleaned_data['size']:
        orm_operator = 'size__{}'.format(
            ORM_OPERATORS[operator]
        )
        qs = qs.filter(**{orm_operator: value})
    qs = _filter_form_dates(qs, form, ('created_at', 'completed_at'))
    if form.cleaned_data.get('key'):
        key_q = Q(key__icontains=form.cleaned_data['key'][0])
        for other in form.cleaned_data['key'][1:]:
            key_q &= Q(key__icontains=other)
        qs = qs.filter(key_q)
    if form.cleaned_data['download']:
        if form.cleaned_data['download'] == 'microsoft':
            qs = qs.filter(microsoft_download=True)
    include_bucket_names = []
    for operator, bucket_name in form.cleaned_data['bucket_name']:
        if operator == '!':
            qs = qs.exclude(bucket_name=bucket_name)
        else:
            include_bucket_names.append(bucket_name)
    if include_bucket_names:
        qs = qs.filter(bucket_name__in=include_bucket_names)

    files = []
    batch_size = settings.API_FILES_BATCH_SIZE
    start = (page - 1) * batch_size
    end = start + batch_size

    aggregates_numbers = qs.aggregate(
        count=Count('id'),
        size_avg=Avg('size'),
        size_sum=Sum('size'),
    )
    time_avg = qs.filter(
        completed_at__isnull=False
    ).aggregate(
        time_avg=Avg(F('completed_at') - F('created_at')),
    )['time_avg']
    if time_avg is not None:
        time_avg = time_avg.total_seconds()
    aggregates = {
        'files': {
            'count': aggregates_numbers['count'],
            'incomplete': qs.filter(completed_at__isnull=True).count(),
            'size': {
                'average': aggregates_numbers['size_avg'],
                'sum': aggregates_numbers['size_sum'],
            },
            'time': {
                'average': time_avg,
            }
        }
    }

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

    total = aggregates['files']['count']

    context = {
        'files': files,
        'aggregates': aggregates,
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
    files_qs = FileUpload.objects.all()
    if not all_uploads:
        upload_qs = upload_qs.filter(user=request.user)
        files_qs = files_qs.filter(upload__user=request.user)

    def count_and_size(qs, start, end):
        sub_qs = qs.filter(created_at__gte=start, created_at__lt=end)
        return {
            'count': sub_qs.count(),
            'total_size': sub_qs.aggregate(size=Sum('size'))['size'],
        }

    today = timezone.now()
    start_today = today.replace(hour=0, minute=0, second=0)
    start_yesterday = start_today - datetime.timedelta(days=1)
    start_this_month = today.replace(day=1)
    start_this_year = start_this_month.replace(month=1)

    numbers['uploads'] = {
        'all_uploads': all_uploads,
        'today': count_and_size(upload_qs, start_today, today),
        'yesterday': count_and_size(upload_qs, start_yesterday, start_today),
        'this_month': count_and_size(upload_qs, start_this_month, today),
        'this_year': count_and_size(upload_qs, start_this_year, today),
    }
    numbers['files'] = {
        'today': count_and_size(files_qs, start_today, today),
        'yesterday': count_and_size(files_qs, start_yesterday, start_today),
        'this_month': count_and_size(files_qs, start_this_month, today),
        'this_year': count_and_size(files_qs, start_this_year, today),
    }

    missing_qs = MissingSymbol.objects.all()
    microsoft_qs = MicrosoftDownload.objects.all()

    def count_missing(start, end):
        qs = missing_qs.filter(modified_at__gte=start, modified_at__lt=end)
        return {
            'count': qs.count(),
        }

    def count_microsoft(start, end):
        qs = microsoft_qs.filter(created_at__gte=start, created_at__lt=end)
        return {
            'count': qs.count(),
        }

    numbers['downloads'] = {
        'missing': {
            'today': count_missing(start_today, today),
            'yesterday': count_missing(start_yesterday, start_today),
            'this_month': count_missing(start_this_month, today),
            'this_year': count_missing(start_this_year, today),
        },
        'microsoft': {
            'today': count_microsoft(start_today, today),
            'yesterday': count_microsoft(start_yesterday, start_today),
            'this_month': count_microsoft(start_this_month, today),
            'this_year': count_microsoft(start_this_year, today),
        },
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
        'BENCHMARKING_ENABLED',
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


@api_login_required
@api_superuser_required
def current_versions(request):
    """return a JSON dict of a selection of keys and their versions
    """
    context = {
        'versions': []
    }
    with connection.cursor() as cursor:
        cursor.execute('select version()')
        row = cursor.fetchone()
        value, = row
        context['versions'].append({
            'key': 'PostgreSQL',
            'value': value.split(' on ')[0].replace('PostgreSQL', '').strip()
        })
    context['versions'].append({
        'key': 'Tecken',
        'value': dockerflow_get_version(settings.BASE_DIR)
    })
    context['versions'].append({
        'key': 'Django',
        'value': get_version(),
    })
    redis_store_info = get_redis_connection('store').info()
    context['versions'].append({
        'key': 'Redis Store',
        'value': redis_store_info['redis_version']
    })
    try:
        redis_cache_info = get_redis_connection('default').info()
    except NotImplementedError:
        redis_cache_info = {'redis_version': 'fakeredis'}
    context['versions'].append({
        'key': 'Redis Cache',
        'value': redis_cache_info['redis_version']
    })

    context['versions'].sort(key=lambda x: x['key'])
    return http.JsonResponse(context)


def downloads_missing(request):
    context = {
    }
    form = forms.DownloadsMissingForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse(
            {'errors': pagination_form.errors},
            status=400
        )

    qs = MissingSymbol.objects.all()
    qs = filter_missing_symbols(qs, form)

    batch_size = settings.API_DOWNLOADS_MISSING_BATCH_SIZE
    context['batch_size'] = batch_size

    page = pagination_form.cleaned_data['page']
    start = (page - 1) * batch_size
    end = start + batch_size

    context['aggregates'] = {
        'missing': {
            'total': qs.count(),
        },
    }
    today = timezone.now()
    for days in (1, 5, 10, 30):
        count = qs.filter(
            modified_at__gte=today - datetime.timedelta(days=days)
        ).count()
        context['aggregates']['missing'][f'last_{days}_days'] = count

    context['total'] = context['aggregates']['missing']['total']

    rows = []
    for missing in qs.order_by('-modified_at')[start:end]:
        rows.append({
            'id': missing.id,
            'symbol': missing.symbol,
            'debugid': missing.debugid,
            'filename': missing.filename,
            'code_file': missing.code_file,
            'code_id': missing.code_id,
            'count': missing.count,
            'modified_at': missing.modified_at,
            'created_at': missing.created_at,
        })
    context['missing'] = rows

    return http.JsonResponse(context)


def filter_missing_symbols(qs, form):
    qs = _filter_form_dates(qs, form, ('created_at', 'modified_at'))
    for operator, value in form.cleaned_data['count']:
        orm_operator = 'count__{}'.format(
            ORM_OPERATORS[operator]
        )
        qs = qs.filter(**{orm_operator: value})
    for key in ('symbol', 'debugid', 'filename'):
        if form.cleaned_data[key]:
            qs = qs.filter(**{f'{key}__contains': form.cleaned_data[key]})
    return qs


def downloads_microsoft(request):
    context = {}
    form = forms.DownloadsMicrosoftForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({'errors': form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse(
            {'errors': pagination_form.errors},
            status=400
        )

    qs = MicrosoftDownload.objects.all()
    qs = filter_microsoft_downloads(qs, form)

    batch_size = settings.API_DOWNLOADS_MICROSOFT_BATCH_SIZE
    context['batch_size'] = batch_size

    page = pagination_form.cleaned_data['page']
    start = (page - 1) * batch_size
    end = start + batch_size

    file_uploads_aggregates = qs.filter(file_upload__isnull=False).aggregate(
        count=Count('file_upload_id'),
        size_sum=Sum('file_upload__size'),
        size_avg=Avg('file_upload__size'),
    )
    context['aggregates'] = {
        'microsoft_downloads': {
            'total': qs.count(),
            'file_uploads': {
                'count': file_uploads_aggregates['count'],
                'size': {
                    'sum': file_uploads_aggregates['size_sum'],
                    'average': file_uploads_aggregates['size_avg'],
                }
            },
            'errors': qs.filter(error__isnull=False).count(),
            'skipped': qs.filter(skipped=True).count(),
        },
    }

    context['total'] = context['aggregates']['microsoft_downloads']['total']

    rows = []
    qs = qs.select_related('missing_symbol', 'file_upload')
    for download in qs.order_by('-created_at')[start:end]:
        missing = download.missing_symbol
        file_upload = download.file_upload
        if file_upload is not None:
            # Then it's an instance of FileUpload. Turn that into a dict.
            file_upload = {
                'id': file_upload.id,
                'bucket_name': file_upload.bucket_name,
                'key': file_upload.key,
                'update': file_upload.update,
                'compressed': file_upload.compressed,
                'size': file_upload.size,
                'created_at': file_upload.created_at,
                'completed_at': file_upload.completed_at,
            }
        rows.append({
            'id': download.id,
            'missing_symbol': {
                'symbol': missing.symbol,
                'debugid': missing.debugid,
                'filename': missing.filename,
                'code_file': missing.code_file,
                'code_id': missing.code_id,
                'count': missing.count,
            },
            'file_upload': file_upload,
            'created_at': download.created_at,
            'completed_at': download.completed_at,
            'error': download.error,
        })

    context['microsoft_downloads'] = rows

    return http.JsonResponse(context)


def filter_microsoft_downloads(qs, form):
    qs = _filter_form_dates(qs, form, ('created_at', 'modified_at'))
    for key in ('symbol', 'debugid', 'filename'):
        if form.cleaned_data[key]:
            qs = qs.filter(**{
                f'missing_symbol__{key}__contains': form.cleaned_data[key]
            })
    if form.cleaned_data['state'] == 'specific-error':
        specific_error = form.cleaned_data['error']
        qs = qs.filter(error__icontains=specific_error)
    elif form.cleaned_data['state'] == 'errored':
        qs = qs.filter(error__isnull=False)
    elif form.cleaned_data['state'] == 'file-upload':
        qs = qs.filter(file_upload__isnull=False)
    elif form.cleaned_data['state'] == 'no-file-upload':
        qs = qs.filter(file_upload__isnull=True)
    elif form.cleaned_data['state']:  # pragma: no cover
        raise NotImplementedError(form.cleaned_data['state'])

    return qs
