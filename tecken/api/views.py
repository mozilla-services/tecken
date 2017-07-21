# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import logging

from django import http
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission, User, Group
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

from tecken.tokens.models import Token
from tecken.upload.models import Upload
from tecken.base.decorators import api_login_required, api_permission_required
from .forms import TokenForm, UserEditForm

logger = logging.getLogger('tecken')


def auth(request):
    context = {}
    if request.user.is_authenticated:
        context['user'] = {
            'email': request.user.email,
            'is_active': request.user.is_active,
            'is_superuser': request.user.is_superuser,
        }
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
    )
    all_user_permissions = request.user.get_all_permissions()
    possible_permissions = [
        x for x in all_permissions
        if f'{x.content_type}.{x.codename}' in all_user_permissions
    ]

    if request.method == 'POST':
        form = TokenForm(request.POST)
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

    context = {
        'tokens': [],
        'permissions': serialize_permissions(possible_permissions),
    }
    qs = Token.objects.filter(user=request.user)
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


@require_http_methods(['DELETE'])
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

    group_permissions = {}

    def groups_to_permissions(groups):
        permissions = []
        for group in groups:
            if group.id not in group_permissions:
                permission_names = [
                    _serialize_permission(x) for x in group.permissions.all()
                ]
                group_permissions[group.id] = permission_names
            permissions.extend(group_permissions[group.id])
        return sorted(permissions)

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


@api_login_required
@api_permission_required('users.change_user')
def edit_user(request, id):
    user = get_object_or_404(User, id=id)

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
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
    return http.JsonResponse(context)
