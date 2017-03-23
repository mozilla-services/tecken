# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from functools import wraps

from django.shortcuts import get_object_or_404
from django.utils.decorators import available_attrs
from guardian.utils import get_403_or_None


def permission_required(perm, klass, **params):
    """
    A decorator that will raise a 404 if an object with the given
    view parameters isn't found or if the request user doesn't have
    the given permission for the object.

    E.g. for checking if the request user is allowed to change a user
    with the given username::

        @permission_required('auth.change_user', User)
        def change_user(request, username):
            # can use get() directly since get_object_or_404 was already called
            # in the decorator and would have raised a Http404 if not found
            user = User.objects.get(username=username)
            return render(request, 'change_user.html', context={'user': user})

    """
    ignore = params.pop('ignore', [])

    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            filters = {}
            for kwarg, kwvalue in list(kwargs.items()):
                if kwarg in ignore:
                    continue
                filters[kwarg] = kwvalue
            obj = get_object_or_404(klass, **filters)
            response = get_403_or_None(
                request,
                perms=[perm],
                obj=obj,
                return_403=True,
            )
            if response:
                return response
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def full_perm(model, perm):
    return '%s.%s_%s' % (model._meta.app_label, perm, model._meta.model_name)


def view_permission_required(model, **params):
    return permission_required(full_perm(model, 'view'), model, **params)


def add_permission_required(model, **params):
    return permission_required(full_perm(model, 'add'), model, **params)


def change_permission_required(model, **params):
    return permission_required(full_perm(model, 'change'), model, **params)


def delete_permission_required(model, **params):
    return permission_required(full_perm(model, 'delete'), model, **params)


def modified_date(view_func):
    """
    A decorator that when applied to a view using a TemplateResponse
    will look for a context variable (by default "modified_date") to
    set the header (by default "X-ATMO-Modified-Date") with the ISO
    formatted value.

    This is useful to check for modification on the client side.
    The end result will be a header like this:

    X-ATMO-Modified-Date: 2017-03-14T10:48:53+00:00
    """
    context_var = 'modified_date'
    header = 'X-ATMO-Modified-Date'

    @wraps(view_func, assigned=available_attrs(view_func))
    def _wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        # This requires the use of TemplateResponse
        modified_date = getattr(response, 'context_data', {}).get(context_var)
        if modified_date is not None:
            response[header] = modified_date.isoformat()
        return response
    return _wrapped_view
