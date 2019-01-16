# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import logging
from urllib.parse import urlparse, urlunparse

import markus
from dockerflow.version import get_version as dockerflow_get_version
from django_redis import get_redis_connection

from django import http
from django import get_version
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import Permission, User, Group
from django.db.models import Aggregate, Count, Q, Sum, Avg, F, Min
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect
from django.db import connection
from django.core.exceptions import PermissionDenied
from django.core.cache import cache

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload, UploadsCreated
from tecken.upload.views import get_possible_bucket_urls
from tecken.storage import StorageBucket
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.symbolicate.views import get_symbolication_count_key
from tecken.base.decorators import (
    api_login_required,
    api_permission_required,
    api_require_http_methods,
    api_superuser_required,
)
from tecken.base.utils import filesizeformat
from . import forms

logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


class SumCardinality(Aggregate):
    template = "SUM(CARDINALITY(%(expressions)s))"


ORM_OPERATORS = {"<=": "lte", ">=": "gte", "=": "exact", "<": "lt", ">": "gt"}


def _filter_form_dates(qs, form, keys):
    for key in keys:
        for operator, value in form.cleaned_data.get(key, []):
            if value is None:
                orm_operator = f"{key}__isnull"
                qs = qs.filter(**{orm_operator: True})
            elif operator == "=" and (
                not isinstance(value, datetime.datetime)
                or value.hour == 0
                and value.minute == 0
            ):
                # When querying on a specific day, make it a little easier
                qs = qs.filter(
                    **{
                        f"{key}__gte": value,
                        f"{key}__lt": value + datetime.timedelta(days=1),
                    }
                )
            else:
                if operator == ">":
                    # Because we use microseconds in the ORM, but when
                    # datetimes are passed back end forth in XHR, the
                    # datetimes are converted with isoformat() which
                    # drops microseconds. Therefore add 1 second to
                    # avoid matching the latest date.
                    value += datetime.timedelta(seconds=1)
                orm_operator = "{}__{}".format(key, ORM_OPERATORS[operator])
                qs = qs.filter(**{orm_operator: value})
    return qs


@metrics.timer_decorator("api", tags=["endpoint:auth"])
def auth(request):
    context = {}
    if request.user.is_authenticated:
        context["user"] = {
            "email": request.user.email,
            "is_active": request.user.is_active,
            "is_superuser": request.user.is_superuser,
            "permissions": [],
        }
        permissions = Permission.objects.filter(
            codename__in=(
                "view_all_uploads",
                "upload_symbols",
                "upload_try_symbols",
                "manage_tokens",
            )
        )
        user_permissions = request.user.get_all_permissions()
        for permission in permissions.select_related("content_type"):
            codename = f"{permission.content_type.app_label}.{permission.codename}"
            if codename in user_permissions:
                context["user"]["permissions"].append(
                    {"id": permission.id, "codename": codename, "name": permission.name}
                )

        # do we need to add the one for managing tokens?
        context["sign_out_url"] = request.build_absolute_uri(reverse("oidc_logout"))
    else:
        if settings.DEBUG:  # pragma: no cover
            if (
                settings.OIDC_RP_CLIENT_ID == "mustbesomething"
                or settings.OIDC_RP_CLIENT_SECRET == "mustbesomething"
            ):
                # When you start up Tecken for the very first time and
                # you haven't configured OIDC credentials, let's make a stink
                # about this.
                print(
                    "WARNING!\nSeems you haven't configured the necessary "
                    "OIDC environment variables OIDC_RP_CLIENT_ID and "
                    "OIDC_RP_CLIENT_SECRET.\n"
                    "Check your .env file and make sure you have something "
                    "set for DJANGO_OIDC_RP_CLIENT_ID and "
                    "DJANGO_OIDC_RP_CLIENT_SECRET.\n"
                    "Signing in won't work until this is set.\n"
                )
        context["sign_in_url"] = request.build_absolute_uri(
            reverse("oidc_authentication_init")
        )
        context["user"] = None
    return http.JsonResponse(context)


@api_login_required
@metrics.timer_decorator("api", tags=["endpoint:possible_upload_urls"])
def possible_upload_urls(request):
    context = {"urls": []}
    for url, private_or_public in get_possible_bucket_urls(request.user):
        bucket_info = StorageBucket(url)

        # In this context, a "private bucket" is one we *don't* just talk to via
        # plain HTTP. I.e. we *can* upload to it at all.
        assert bucket_info.private

        context["urls"].append(
            {
                "url": url,
                "bucket_name": bucket_info.name,
                "is_google_cloud_storage": bucket_info.is_google_cloud_storage,
                "private": private_or_public == "private",
                "default": url == settings.UPLOAD_DEFAULT_URL,
            }
        )
        context["urls"].reverse()  # Default first
    return http.JsonResponse(context)


@api_login_required
@api_permission_required("tokens.manage_tokens")
def tokens(request):
    def serialize_permissions(permissions):
        return [{"name": x.name, "id": x.id} for x in permissions]

    all_permissions = (
        Permission.objects.get(codename="upload_symbols"),
        Permission.objects.get(codename="upload_try_symbols"),
        Permission.objects.get(codename="view_all_uploads"),
        Permission.objects.get(codename="manage_tokens"),
    )
    all_user_permissions = request.user.get_all_permissions()
    possible_permissions = [
        x
        for x in all_permissions
        if (
            f"{x.content_type}.{x.codename}" in all_user_permissions
            or request.user.is_superuser
        )
    ]

    if request.method == "POST":
        form = forms.TokenForm(request.POST)
        if form.is_valid():
            # Check that none of the sent permissions isn't possible
            for permission in form.cleaned_data["permissions"]:
                if permission not in possible_permissions:
                    raise PermissionDenied(f"{permission.name} not a valid permission")
            expires_at = timezone.now() + datetime.timedelta(
                days=form.cleaned_data["expires"]
            )
            token = Token.objects.create(
                user=request.user,
                expires_at=expires_at,
                notes=form.cleaned_data["notes"].strip(),
            )
            for permission in form.cleaned_data["permissions"]:
                token.permissions.add(permission)

            return http.JsonResponse({"ok": True}, status=201)
        else:
            return http.JsonResponse({"errors": form.errors}, status=400)

    form = forms.TokensForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    filter_state = form.cleaned_data["state"]

    context = {"tokens": [], "permissions": serialize_permissions(possible_permissions)}
    qs = Token.objects.filter(user=request.user)
    # Before we filter the queryset further, use it to calculate counts.
    context["totals"] = {
        "all": qs.count(),
        "active": qs.filter(expires_at__gt=timezone.now()).count(),
        "expired": qs.filter(expires_at__lte=timezone.now()).count(),
    }
    if filter_state == "all":
        pass
    elif filter_state == "expired":
        qs = qs.filter(expires_at__lte=timezone.now())
    else:
        # The default is to only return active ones
        qs = qs.filter(expires_at__gt=timezone.now())

    for token in qs.order_by("-created_at"):
        context["tokens"].append(
            {
                "id": token.id,
                "expires_at": token.expires_at,
                "is_expired": token.is_expired,
                "key": token.key,
                "permissions": serialize_permissions(token.permissions.all()),
                "notes": token.notes,
                "created_at": token.created_at,
            }
        )

    return http.JsonResponse(context)


@api_require_http_methods(["DELETE"])
@api_login_required
def delete_token(request, id):
    if request.user.is_superuser:
        token = get_object_or_404(Token, id=id)
    else:
        token = get_object_or_404(Token, id=id, user=request.user)
    token.delete()

    return http.JsonResponse({"ok": True})


@api_require_http_methods(["POST"])
@api_login_required
def extend_token(request, id):
    token = get_object_or_404(Token, id=id, user=request.user)
    form = forms.ExtendTokenForm(request.POST)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    days = form.cleaned_data["days"] or 365

    token.expires_at = token.expires_at + datetime.timedelta(days=days)
    token.save()

    return http.JsonResponse({"ok": True, "days": days})


def _serialize_permission(p):
    return {"id": p.id, "name": p.name}


def _serialize_group(group):
    return {
        "id": group.id,
        "name": group.name,
        "permissions": [_serialize_permission(x) for x in group.permissions.all()],
    }


@api_login_required
@api_permission_required("users.change_user")
def users(request):
    context = {"users": []}

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
                    all_group_permissions[group.id].append(_serialize_permission(perm))
            for permission in all_group_permissions[group.id]:
                if permission["id"] in permission_ids:
                    continue
                permission_ids.add(permission["id"])
                all_permissions.append(permission)
        return sorted(all_permissions, key=lambda x: x["name"])

    # Make a map of user_id to count of Token objects
    tokens_count = {}
    for rec in Token.objects.values("user").annotate(count=Count("user")):
        tokens_count[rec["user"]] = rec["count"]
    uploads_count = {}
    for rec in Upload.objects.values("user").annotate(count=Count("user")):
        uploads_count[rec["user"]] = rec["count"]

    qs = User.objects.all()
    for user in qs.order_by("-last_login"):
        context["users"].append(
            {
                "id": user.id,
                "email": user.email,
                "last_login": user.last_login,
                "date_joined": user.date_joined,
                "is_superuser": user.is_superuser,
                "is_active": user.is_active,
                "no_uploads": uploads_count.get(user.id, 0),
                "no_tokens": tokens_count.get(user.id, 0),
                "groups": [_serialize_group(x) for x in user.groups.all()],
                "permissions": groups_to_permissions(user.groups.all()),
            }
        )

    return http.JsonResponse(context)


@csrf_protect
@api_login_required
@api_permission_required("users.change_user")
def edit_user(request, id):
    user = get_object_or_404(User, id=id)

    if request.method == "POST":
        form = forms.UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            # Remove all the groups that user might have been in before
            groups = form.cleaned_data["groups"]
            for group in set(user.groups.all()) - set(groups):
                user.groups.remove(group)
            for group in set(groups) - set(user.groups.all()):
                user.groups.add(group)
            return http.JsonResponse({"ok": True}, status=200)
        else:
            return http.JsonResponse({"errors": form.errors}, status=400)

    context = {}
    context["user"] = {
        "id": user.id,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "email": user.email,
        "groups": [_serialize_group(x) for x in user.groups.all()],
    }
    context["groups"] = [_serialize_group(x) for x in Group.objects.all()]
    from django.middleware.csrf import get_token

    context["csrf_token"] = get_token(request)
    return http.JsonResponse(context)


@metrics.timer_decorator("api", tags=["endpoint:uploads"])
@api_login_required
def uploads(request):
    context = {
        "uploads": [],
        "can_view_all": request.user.has_perm("upload.view_all_uploads"),
    }

    form = forms.UploadsForm(request.GET, valid_sorts=("size", "created_at"))
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    qs = Upload.objects.all()
    qs = filter_uploads(qs, context["can_view_all"], request.user, form)

    batch_size = settings.API_UPLOADS_BATCH_SIZE

    page = pagination_form.cleaned_data["page"]
    start = (page - 1) * batch_size
    end = start + batch_size

    if context["can_view_all"] and not any(form.cleaned_data.values()):
        # If you can view ALL uploads and there's no filtering, we can use
        # UploadsCreated instead which is much more efficient.
        aggregates_numbers = UploadsCreated.objects.aggregate(
            count=Sum("count"),
            size_sum=Sum("size"),
            skipped_sum=Sum("skipped"),
            files=Sum("files"),
        )
        context["aggregates"] = {
            "uploads": {
                "count": aggregates_numbers["count"],
                "size": {"sum": aggregates_numbers["size_sum"]},
                "skipped": {"sum": aggregates_numbers["skipped_sum"]},
            },
            "files": {"count": aggregates_numbers["files"]},
        }
        # Do this later to avoid ZeroDivisionError
        if aggregates_numbers["count"]:
            context["aggregates"]["uploads"]["size"]["average"] = (
                aggregates_numbers["size_sum"] / aggregates_numbers["count"]
            )
        else:
            context["aggregates"]["uploads"]["size"]["average"] = None

    else:
        aggregates_numbers = qs.aggregate(
            count=Count("id"),
            size_avg=Avg("size"),
            size_sum=Sum("size"),
            skipped_sum=SumCardinality("skipped_keys"),
        )
        context["aggregates"] = {
            "uploads": {
                "count": aggregates_numbers["count"],
                "size": {
                    "average": aggregates_numbers["size_avg"],
                    "sum": aggregates_numbers["size_sum"],
                },
                "skipped": {"sum": aggregates_numbers["skipped_sum"]},
            }
        }
        file_uploads_qs = FileUpload.objects.filter(upload__in=qs)
        context["aggregates"]["files"] = {"count": file_uploads_qs.count()}

    if form.cleaned_data.get("order_by"):
        order_by = form.cleaned_data["order_by"]
    else:
        order_by = {"sort": "created_at", "reverse": True}

    rows = []
    order_by_string = ("-" if order_by["reverse"] else "") + order_by["sort"]
    for upload in qs.select_related("user").order_by(order_by_string)[start:end]:
        rows.append(
            {
                "id": upload.id,
                "user": {"email": upload.user.email},
                "filename": upload.filename,
                "size": upload.size,
                "bucket_name": upload.bucket_name,
                "bucket_region": upload.bucket_region,
                "bucket_endpoint_url": upload.bucket_endpoint_url,
                "skipped_keys": upload.skipped_keys or [],
                "ignored_keys": upload.ignored_keys or [],
                "try_symbols": upload.try_symbols,
                "download_url": upload.download_url,
                "redirect_urls": upload.redirect_urls or [],
                "completed_at": upload.completed_at,
                "created_at": upload.created_at,
            }
        )
    # Make a FileUpload aggregate count on these uploads
    file_uploads = FileUpload.objects.filter(upload_id__in=[x["id"] for x in rows])
    # Convert it to a dict
    file_upload_counts_map = {
        x["upload"]: x["count"]
        for x in file_uploads.values("upload").annotate(count=Count("upload"))
    }
    # Convert it to a dict
    file_upload_counts_map = {
        x["upload"]: x["count"]
        for x in file_uploads.values("upload")
        .filter(completed_at__isnull=False)
        .annotate(count=Count("upload"))
    }
    # And a dict of all the incomplete ones
    file_upload_incomplete_counts_map = {
        x["upload"]: x["count"]
        for x in file_uploads.filter(completed_at__isnull=True)
        .values("upload")
        .annotate(count=Count("upload"))
    }
    for upload in rows:
        upload["files_count"] = file_upload_counts_map.get(upload["id"], 0)
        upload["files_incomplete_count"] = file_upload_incomplete_counts_map.get(
            upload["id"], 0
        )

    context["uploads"] = rows
    context["total"] = context["aggregates"]["uploads"]["count"]
    context["batch_size"] = batch_size
    context["order_by"] = order_by

    return http.JsonResponse(context)


def filter_uploads(qs, can_view_all, user, form):
    # Force the filtering to *your* symbols unless you have the
    # 'view_all_uploads' permission.
    if can_view_all:
        if form.cleaned_data["user"]:
            operator, user = form.cleaned_data["user"]
            qs_function = qs.exclude if operator == "!" else qs.filter
            # If the form managed to convert it to an instance,
            # the select queried doesn't need to do a join.
            # Otherwise do a regex on its email.
            if isinstance(user, str):
                qs = qs_function(user__email__icontains=user)
            else:
                qs = qs_function(user=user)
    else:
        qs = qs.filter(user=user)
    for operator, value in form.cleaned_data["size"]:
        orm_operator = "size__{}".format(ORM_OPERATORS[operator])
        qs = qs.filter(**{orm_operator: value})
    qs = _filter_form_dates(qs, form, ("created_at", "completed_at"))
    return qs


@metrics.timer_decorator("api", tags=["endpoint:upload"])
@api_login_required
def upload(request, id):
    obj = get_object_or_404(Upload, id=id)
    # You're only allowed to see this if it's yours or you have the
    # 'view_all_uploads' permission.
    if not (
        obj.user == request.user or request.user.has_perm("upload.view_all_uploads")
    ):
        raise PermissionDenied("Insufficient access to view this upload")

    def make_upload_dict(upload_obj):
        file_uploads_qs = FileUpload.objects.filter(upload=upload_obj)
        file_uploads = []
        for file_upload in file_uploads_qs.order_by("created_at"):
            file_uploads.append(
                {
                    "id": file_upload.id,
                    "bucket_name": file_upload.bucket_name,
                    "key": file_upload.key,
                    "update": file_upload.update,
                    "compressed": file_upload.compressed,
                    "size": file_upload.size,
                    "microsoft_download": file_upload.microsoft_download,
                    "completed_at": file_upload.completed_at,
                    "created_at": file_upload.created_at,
                }
            )
        return {
            "id": upload_obj.id,
            "filename": upload_obj.filename,
            "user": {"id": upload_obj.user.id, "email": upload_obj.user.email},
            "size": upload_obj.size,
            "bucket_name": upload_obj.bucket_name,
            "bucket_region": upload_obj.bucket_region,
            "bucket_endpoint_url": upload_obj.bucket_endpoint_url,
            "skipped_keys": upload_obj.skipped_keys or [],
            "ignored_keys": upload_obj.ignored_keys or [],
            "try_symbols": upload_obj.try_symbols,
            "download_url": upload_obj.download_url,
            "redirect_urls": upload_obj.redirect_urls or [],
            "completed_at": upload_obj.completed_at,
            "created_at": upload_obj.created_at,
            "file_uploads": file_uploads,
        }

    upload_dict = make_upload_dict(obj)

    related_qs = Upload.objects.exclude(id=obj.id).filter(size=obj.size, user=obj.user)
    if obj.content_hash:
        related_qs = related_qs.filter(content_hash=obj.content_hash)
    else:
        # The `content_hash` attribute is a new field as of Oct 10 2017.
        # So if the upload doesn't have that, use the filename which is
        # less than ideal.
        related_qs = related_qs.filter(filename=obj.filename)
    upload_dict["related"] = []
    for related_upload in related_qs.order_by("-created_at"):
        upload_dict["related"].append(make_upload_dict(related_upload))

    context = {"upload": upload_dict}
    return http.JsonResponse(context)


@api_login_required
@api_permission_required("upload.view_all_uploads")
def uploads_created(request):
    context = {"uploads_created": []}

    form = forms.UploadsCreatedForm(request.GET, valid_sorts=("size", "date"))
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    qs = UploadsCreated.objects.all()
    qs = filter_uploads_created(qs, form)

    batch_size = settings.API_UPLOADS_CREATED_BATCH_SIZE

    page = pagination_form.cleaned_data["page"]
    start = (page - 1) * batch_size
    end = start + batch_size

    aggregates_numbers = qs.aggregate(
        count=Sum("count"),
        total=Count("id"),
        size_avg=Avg("size"),
        size=Sum("size"),
        files=Sum("files"),
        skipped=Sum("skipped"),
        ignored=Sum("ignored"),
    )
    context["aggregates"] = {
        "uploads_created": {
            "count": aggregates_numbers["count"],
            "files": aggregates_numbers["files"],
            "size": aggregates_numbers["size"],
            "size_avg": aggregates_numbers["size_avg"],
            "skipped": aggregates_numbers["skipped"],
            "ignored": aggregates_numbers["ignored"],
        }
    }

    if form.cleaned_data.get("order_by"):
        order_by = form.cleaned_data["order_by"]
    else:
        order_by = {"sort": "date", "reverse": True}

    rows = []
    order_by_string = ("-" if order_by["reverse"] else "") + order_by["sort"]
    for created in qs.order_by(order_by_string)[start:end]:
        rows.append(
            {
                "id": created.id,
                "date": created.date,
                "count": created.count,
                "files": created.files,
                "skipped": created.skipped,
                "ignored": created.ignored,
                "size": created.size,
                "size_avg": created.size_avg,
                "created_at": created.created_at,
                # "modified_at": created.modified_at,
            }
        )

    context["uploads_created"] = rows
    context["total"] = aggregates_numbers["total"]
    context["batch_size"] = batch_size
    context["order_by"] = order_by

    return http.JsonResponse(context)


def filter_uploads_created(qs, form):
    for key in ("size", "count"):
        for operator, value in form.cleaned_data[key]:
            orm_operator = "{}__{}".format(key, ORM_OPERATORS[operator])
            qs = qs.filter(**{orm_operator: value})
    qs = _filter_form_dates(qs, form, ("date",))
    return qs


@api_login_required
@api_superuser_required
def uploads_created_backfilled(request):
    """Temporary function that serves two purposes. Ability to see if all the
    UploadsCreated have been backfilled and actually do some backfill."""

    context = {}
    min_uploads = Upload.objects.aggregate(min=Min("created_at"))["min"]
    days_till_today = (timezone.now() - min_uploads).days
    uploads_created_count = UploadsCreated.objects.all().count()
    context["uploads_created_count"] = uploads_created_count
    context["days_till_today"] = days_till_today
    context["backfilled"] = bool(
        uploads_created_count and days_till_today + 1 == uploads_created_count
    )

    if request.method == "POST":
        days = int(request.POST.get("days", 2))
        force = request.POST.get("force", "no") not in ("no", "0", "false")
        start = min_uploads.date()
        today = timezone.now().date()
        context["updated"] = []
        while start <= today:
            if force or not UploadsCreated.objects.filter(date=start).exists():
                record = UploadsCreated.update(start)
                context["updated"].append({"date": record.date, "count": record.count})
                if len(context["updated"]) >= days:
                    break
            start += datetime.timedelta(days=1)
        context["backfilled"] = True
    return http.JsonResponse(context)


@metrics.timer_decorator("api", tags=["endpoint:upload_files"])
@api_login_required
@api_permission_required("upload.view_all_uploads")
def upload_files(request):
    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)
    page = pagination_form.cleaned_data["page"]

    form = forms.FileUploadsForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    qs = FileUpload.objects.all()
    for operator, value in form.cleaned_data["size"]:
        orm_operator = "size__{}".format(ORM_OPERATORS[operator])
        qs = qs.filter(**{orm_operator: value})
    qs = _filter_form_dates(qs, form, ("created_at", "completed_at"))
    if form.cleaned_data.get("key"):
        key_q = Q(key__icontains=form.cleaned_data["key"][0])
        for other in form.cleaned_data["key"][1:]:
            key_q &= Q(key__icontains=other)
        qs = qs.filter(key_q)
    if form.cleaned_data["download"]:
        if form.cleaned_data["download"] == "microsoft":
            qs = qs.filter(microsoft_download=True)
    include_bucket_names = []
    for operator, bucket_name in form.cleaned_data["bucket_name"]:
        if operator == "!":
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
        count=Count("id"), size_avg=Avg("size"), size_sum=Sum("size")
    )
    time_avg = qs.filter(completed_at__isnull=False).aggregate(
        time_avg=Avg(F("completed_at") - F("created_at"))
    )["time_avg"]
    if time_avg is not None:
        time_avg = time_avg.total_seconds()
    aggregates = {
        "files": {
            "count": aggregates_numbers["count"],
            "incomplete": qs.filter(completed_at__isnull=True).count(),
            "size": {
                "average": aggregates_numbers["size_avg"],
                "sum": aggregates_numbers["size_sum"],
            },
            "time": {"average": time_avg},
        }
    }

    upload_ids = set()
    for file_upload in qs.order_by("-created_at")[start:end]:
        files.append(
            {
                "id": file_upload.id,
                "key": file_upload.key,
                "update": file_upload.update,
                "compressed": file_upload.compressed,
                "microsoft_download": file_upload.microsoft_download,
                "size": file_upload.size,
                "bucket_name": file_upload.bucket_name,
                "completed_at": file_upload.completed_at,
                "created_at": file_upload.created_at,
                "upload": file_upload.upload_id,
            }
        )
        if file_upload.upload_id:
            upload_ids.add(file_upload.upload_id)

    uploads = {
        x.id: x for x in Upload.objects.filter(id__in=upload_ids).select_related("user")
    }

    uploads_cache = {}

    def hydrate_upload(upload_id):
        if upload_id:
            if upload_id not in uploads_cache:
                upload = uploads[upload_id]
                uploads_cache[upload_id] = {
                    "id": upload.id,
                    "try_symbols": upload.try_symbols,
                    "user": {"id": upload.user.id, "email": upload.user.email},
                    "created_at": upload.created_at,
                }
            return uploads_cache[upload_id]

    for file_upload in files:
        file_upload["upload"] = hydrate_upload(file_upload["upload"])

    total = aggregates["files"]["count"]

    context = {
        "files": files,
        "aggregates": aggregates,
        "total": total,
        "batch_size": batch_size,
    }

    return http.JsonResponse(context)


@metrics.timer_decorator("api", tags=["endpoint:upload_file"])
@api_login_required
def upload_file(request, id):
    file_upload = get_object_or_404(FileUpload, id=id)
    # You're only allowed to see this if it's yours or you have the
    # 'view_all_uploads' permission.
    if not (
        (file_upload.upload and file_upload.upload.user == request.user)
        or request.user.has_perm("upload.view_all_uploads")
    ):
        raise PermissionDenied("Insufficient access to view this file")

    symbol, debugid, filename = file_upload.key.split("/")[-3:]
    url = reverse("download:download_symbol", args=(symbol, debugid, filename))
    if file_upload.upload and file_upload.upload.try_symbols:
        url += "?try"

    file_dict = {
        "id": file_upload.id,
        "bucket_name": file_upload.bucket_name,
        "key": file_upload.key,
        "update": file_upload.update,
        "compressed": file_upload.compressed,
        "size": file_upload.size,
        "url": url,
        "completed_at": file_upload.completed_at,
        "created_at": file_upload.created_at,
        "upload": None,
        "microsoft_download": None,
    }

    if file_upload.upload:
        upload_obj = file_upload.upload
        file_dict["upload"] = {
            "id": upload_obj.id,
            "filename": upload_obj.filename,
            "user": {"id": upload_obj.user.id, "email": upload_obj.user.email},
            "size": upload_obj.size,
            "bucket_name": upload_obj.bucket_name,
            "bucket_region": upload_obj.bucket_region,
            "bucket_endpoint_url": upload_obj.bucket_endpoint_url,
            "skipped_keys": upload_obj.skipped_keys or [],
            "ignored_keys": upload_obj.ignored_keys or [],
            "download_url": upload_obj.download_url,
            "redirect_urls": upload_obj.redirect_urls or [],
            "created_at": upload_obj.created_at,
            "completed_at": upload_obj.completed_at,
        }

    if file_upload.microsoft_download:  # a bool
        try:
            microsoft_download = MicrosoftDownload.objects.get(file_upload=file_upload)
            file_dict["microsoft_download"] = {
                "id": microsoft_download.id,
                "url": microsoft_download.url,
                "error": microsoft_download.error,
                "skipped": microsoft_download.skipped,
                "created_at": microsoft_download.created_at,
                "completed_at": microsoft_download.completed_at,
            }
        except MicrosoftDownload.DoesNotExist:
            pass

    context = {"file": file_dict}
    return http.JsonResponse(context)


@metrics.timer_decorator("api", tags=["endpoint:stats"])
@api_login_required
def stats(request):
    numbers = {}

    all_uploads = request.user.has_perm("upload.can_view_all")

    today = timezone.now()
    start_today = today.replace(hour=0, minute=0, second=0)
    start_yesterday = start_today - datetime.timedelta(days=1)
    last_30_days = today - datetime.timedelta(days=30)

    if not all_uploads:
        with metrics.timer("api_stats", tags=["section:your_uploads"]):
            # If it's an individual user, they can only see their own uploads and
            # thus can't use UploadsCreated.
            upload_qs = Upload.objects.filter(user=request.user)
            files_qs = FileUpload.objects.filter(upload__user=request.user)

            def count_and_size(qs, start, end):
                sub_qs = qs.filter(created_at__gte=start, created_at__lt=end)
                return sub_qs.aggregate(count=Count("id"), total_size=Sum("size"))

            def count(qs, start, end):
                sub_qs = qs.filter(created_at__gte=start, created_at__lt=end)
                return sub_qs.aggregate(count=Count("id"))

            numbers["uploads"] = {
                "all_uploads": all_uploads,
                "today": count_and_size(upload_qs, start_today, today),
                "yesterday": count_and_size(upload_qs, start_yesterday, start_today),
                "last_30_days": count_and_size(upload_qs, last_30_days, today),
            }
            numbers["files"] = {
                "today": count(files_qs, start_today, today),
                "yesterday": count(files_qs, start_yesterday, start_today),
                "last_30_days": count(files_qs, last_30_days, today),
            }
    else:
        with metrics.timer("api_stats", tags=["section:all_uploads"]):

            def count_and_size(start, end):
                return UploadsCreated.objects.filter(
                    date__gte=start.date(), date__lt=end.date()
                ).aggregate(
                    count=Sum("count"), total_size=Sum("size"), files=Sum("files")
                )

            _today = count_and_size(today, today + datetime.timedelta(days=1))
            _yesterday = count_and_size(today - datetime.timedelta(days=1), today)
            count_last_30_days = count_and_size(
                last_30_days, today + datetime.timedelta(days=1)
            )

            numbers["uploads"] = {
                "all_uploads": all_uploads,
                "today": {"count": _today["count"], "total_size": _today["total_size"]},
                "yesterday": {
                    "count": _yesterday["count"],
                    "total_size": _yesterday["total_size"],
                },
                "last_30_days": {
                    "count": count_last_30_days["count"],
                    "total_size": count_last_30_days["total_size"],
                },
            }
            numbers["files"] = {
                "today": {"count": _today["files"]},
                "yesterday": {"count": _yesterday["files"]},
                "last_30_days": {"count": count_last_30_days["files"]},
            }

    with metrics.timer("api_stats", tags=["section:all_missing_downloads"]):
        # When doing aggregates on rows that don't exist you can get a None instead
        # of 0. Only really happens in cases where you have extremely little in the
        # database.
        def nones_to_zero(obj):
            for key, value in obj.items():
                if isinstance(value, dict):
                    nones_to_zero(value)
                elif value is None:
                    obj[key] = 0

        nones_to_zero(numbers)

        missing_qs = MissingSymbol.objects.all()
        microsoft_qs = MicrosoftDownload.objects.all()

        def count_missing(start, end, use_cache=True):
            count = None
            if use_cache:
                fmt = "%Y%m%d"
                cache_key = f"count_missing:{start.strftime(fmt)}:{end.strftime(fmt)}"
                count = cache.get(cache_key)
            if count is None:
                qs = missing_qs.filter(modified_at__gte=start, modified_at__lt=end)
                count = qs.count()
                if use_cache:
                    cache.set(cache_key, count, 60 * 60 * 24)
            return {"count": count}

        def count_microsoft(start, end):
            qs = microsoft_qs.filter(created_at__gte=start, created_at__lt=end)
            return {"count": qs.count()}

        numbers["downloads"] = {
            "missing": {
                "today": count_missing(start_today, today, use_cache=False),
                "yesterday": count_missing(start_yesterday, start_today),
                "last_30_days": count_missing(last_30_days, start_today),
            },
            "microsoft": {
                "today": count_microsoft(start_today, today),
                "yesterday": count_microsoft(start_yesterday, start_today),
                "last_30_days": count_microsoft(last_30_days, today),
            },
        }
        # A clever trick! Instead of counting the last_30_days to include now,
        # we count the last 29 days instead up until the start of today.
        # Then, to make it the last 30 days we *add* the "today" count.
        numbers["downloads"]["missing"]["last_30_days"]["count"] += numbers[
            "downloads"
        ]["missing"]["today"]["count"]

    with metrics.timer("api_stats", tags=["section:your_tokens"]):
        # Gather some numbers about tokens
        tokens_qs = Token.objects.filter(user=request.user)
        numbers["tokens"] = {
            "total": tokens_qs.count(),
            "expired": tokens_qs.filter(expires_at__lt=today).count(),
        }

    # Gather some numbers about users
    if request.user.is_superuser:
        with metrics.timer("api_stats", tags=["section:all_users"]):
            users_qs = User.objects.all()
            numbers["users"] = {
                "total": users_qs.count(),
                "superusers": users_qs.filter(is_superuser=True).count(),
                "active": users_qs.filter(is_active=True).count(),
                "not_active": users_qs.filter(is_active=False).count(),
            }

    context = {"stats": numbers}
    return http.JsonResponse(context)


@api_login_required
def stats_uploads(request):
    context = {}

    today = timezone.now().date()
    yesterday = today - datetime.timedelta(days=1)

    start_month = today
    while start_month.day != 1:
        start_month -= datetime.timedelta(days=1)

    def count_uploads(date, end=None):
        qs = UploadsCreated.objects.filter(date__gte=date)
        if end is not None:
            qs = qs.filter(date__lt=end)
        aggregates = qs.aggregate(
            count=Sum("count"), total_size=Sum("size"), files=Sum("files")
        )
        return {
            "count": aggregates["count"] or 0,
            "total_size": aggregates["total_size"] or 0,
            "total_size_human": filesizeformat(aggregates["total_size"] or 0),
            "files": aggregates["files"] or 0,
        }

    context["uploads"] = {
        "today": count_uploads(today),
        "yesterday": count_uploads(yesterday, end=today),
        "this_month": count_uploads(start_month),
    }
    return http.JsonResponse(context)


@api_login_required
def stats_symbolication(request):
    context = {}

    def count_symbolications(prefix, dateobj):
        cache_key = get_symbolication_count_key(prefix, dateobj)
        return cache.get(cache_key, 0)

    today = timezone.now()
    start_today = today.replace(hour=0, minute=0, second=0)
    start_yesterday = start_today - datetime.timedelta(days=1)

    context["symbolications"] = {
        "v4": {
            "today": count_symbolications("v4", today),
            "yesterday": count_symbolications("v4", start_yesterday),
        },
        "v5": {
            "today": count_symbolications("v5", today),
            "yesterday": count_symbolications("v5", start_yesterday),
        },
    }
    return http.JsonResponse(context)


@api_login_required
@api_superuser_required
def current_settings(request):
    """return a JSON dict of a selection of settings to describe the
    current system. These are only accessible to superusers and the settings
    it includes is whitelisted and manually maintained here in this view.
    """
    context = {"settings": []}

    def clean_url(value):
        parsed = urlparse(value)
        if "@" in parsed.netloc:
            # There might be a password in the netloc part.
            # It's extremely unlikely but just in case we ever forget
            # make sure it's never "exposed".
            parts = list(parsed)
            parts[1] = "user:xxxxxx@" + parts[1].split("@", 1)[1]
            return urlunparse(parts)
        return value

    # Only include keys that can never be useful in security context.
    keys = (
        "ENABLE_AUTH0_BLOCKED_CHECK",
        "ENABLE_TOKENS_AUTHENTICATION",
        "ENABLE_DOWNLOAD_FROM_MICROSOFT",
        "ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS",
        "DOWNLOAD_FILE_EXTENSIONS_WHITELIST",
        "BENCHMARKING_ENABLED",
        "ENABLE_STORE_MISSING_SYMBOLS",
    )
    for key in keys:
        value = getattr(settings, key)
        context["settings"].append({"key": key, "value": value})

    # Now for some oddballs
    context["settings"].append(
        {"key": "UPLOAD_DEFAULT_URL", "value": clean_url(settings.UPLOAD_DEFAULT_URL)}
    )
    context["settings"].append(
        {
            "key": "UPLOAD_TRY_SYMBOLS_URL",
            "value": clean_url(settings.UPLOAD_TRY_SYMBOLS_URL),
        }
    )
    context["settings"].append(
        {
            "key": "SYMBOL_URLS",
            "value": json.dumps([clean_url(x) for x in settings.SYMBOL_URLS]),
        }
    )
    context["settings"].append(
        {
            "key": "UPLOAD_URL_EXCEPTIONS",
            "value": json.dumps(
                {k: clean_url(v) for k, v in settings.UPLOAD_URL_EXCEPTIONS.items()}
            ),
        }
    )
    context["settings"].sort(key=lambda x: x["key"])
    return http.JsonResponse(context)


@api_login_required
@api_superuser_required
def current_versions(request):
    """return a JSON dict of a selection of keys and their versions
    """
    context = {"versions": []}
    with connection.cursor() as cursor:
        cursor.execute("select version()")
        row = cursor.fetchone()
        value, = row
        context["versions"].append(
            {
                "key": "PostgreSQL",
                "value": value.split(" on ")[0].replace("PostgreSQL", "").strip(),
            }
        )
    context["versions"].append(
        {"key": "Tecken", "value": dockerflow_get_version(settings.BASE_DIR)}
    )
    context["versions"].append({"key": "Django", "value": get_version()})
    redis_store_info = get_redis_connection("store").info()
    context["versions"].append(
        {"key": "Redis Store", "value": redis_store_info["redis_version"]}
    )
    try:
        redis_cache_info = get_redis_connection("default").info()
    except NotImplementedError:
        redis_cache_info = {"redis_version": "fakeredis"}
    context["versions"].append(
        {"key": "Redis Cache", "value": redis_cache_info["redis_version"]}
    )

    context["versions"].sort(key=lambda x: x["key"])
    return http.JsonResponse(context)


@metrics.timer_decorator("api", tags=["endpoint:downloads_missing"])
def downloads_missing(request):
    context = {}
    form = forms.DownloadsMissingForm(
        request.GET, valid_sorts=("modified_at", "count", "created_at")
    )
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    qs = MissingSymbol.objects.all()
    qs = filter_missing_symbols(qs, form)

    batch_size = settings.API_DOWNLOADS_MISSING_BATCH_SIZE
    context["batch_size"] = batch_size

    page = pagination_form.cleaned_data["page"]
    start = (page - 1) * batch_size
    end = start + batch_size

    # The MissingSymbol class has a classmethod called `total_count`
    # which returns basically the same as `MissingSymbol.objects.count()`
    # but it comes from a counter in the cache instead.
    if any(v for v in form.cleaned_data.values()):
        # Use the queryset
        total_count = qs.count()
    else:
        # No specific filtering was done, we can use the increment counter.
        total_count = MissingSymbol.total_count()

    context["aggregates"] = {"missing": {"total": total_count}}

    today = timezone.now()
    for days in (1, 30):
        count = qs.filter(
            modified_at__gte=today - datetime.timedelta(days=days)
        ).count()
        context["aggregates"]["missing"][f"last_{days}_days"] = count

    context["total"] = context["aggregates"]["missing"]["total"]

    if form.cleaned_data.get("order_by"):
        order_by = form.cleaned_data["order_by"]
    else:
        order_by = {"sort": "modified_at", "reverse": True}

    rows = []
    order_by_string = ("-" if order_by["reverse"] else "") + order_by["sort"]
    for missing in qs.order_by(order_by_string)[start:end]:
        rows.append(
            {
                "id": missing.id,
                "symbol": missing.symbol,
                "debugid": missing.debugid,
                "filename": missing.filename,
                "code_file": missing.code_file,
                "code_id": missing.code_id,
                "count": missing.count,
                "modified_at": missing.modified_at,
                "created_at": missing.created_at,
            }
        )
    context["missing"] = rows
    context["order_by"] = order_by

    return http.JsonResponse(context)


def filter_missing_symbols(qs, form):
    qs = _filter_form_dates(qs, form, ("created_at", "modified_at"))
    for operator, value in form.cleaned_data["count"]:
        orm_operator = "count__{}".format(ORM_OPERATORS[operator])
        qs = qs.filter(**{orm_operator: value})
    for key in ("symbol", "debugid", "filename"):
        if form.cleaned_data[key]:
            qs = qs.filter(**{f"{key}__contains": form.cleaned_data[key]})
    return qs


@metrics.timer_decorator("api", tags=["endpoint:downloads_microsoft"])
def downloads_microsoft(request):
    context = {}
    form = forms.DownloadsMicrosoftForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    pagination_form = forms.PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    qs = MicrosoftDownload.objects.all()
    qs = filter_microsoft_downloads(qs, form)

    batch_size = settings.API_DOWNLOADS_MICROSOFT_BATCH_SIZE
    context["batch_size"] = batch_size

    page = pagination_form.cleaned_data["page"]
    start = (page - 1) * batch_size
    end = start + batch_size

    file_uploads_aggregates = qs.filter(file_upload__isnull=False).aggregate(
        count=Count("file_upload_id"),
        size_sum=Sum("file_upload__size"),
        size_avg=Avg("file_upload__size"),
    )
    context["aggregates"] = {
        "microsoft_downloads": {
            "total": qs.count(),
            "file_uploads": {
                "count": file_uploads_aggregates["count"],
                "size": {
                    "sum": file_uploads_aggregates["size_sum"],
                    "average": file_uploads_aggregates["size_avg"],
                },
            },
            "errors": qs.filter(error__isnull=False).count(),
            "skipped": qs.filter(skipped=True).count(),
        }
    }

    context["total"] = context["aggregates"]["microsoft_downloads"]["total"]

    rows = []
    qs = qs.select_related("missing_symbol", "file_upload")
    for download in qs.order_by("-created_at")[start:end]:
        missing = download.missing_symbol
        file_upload = download.file_upload
        if file_upload is not None:
            # Then it's an instance of FileUpload. Turn that into a dict.
            file_upload = {
                "id": file_upload.id,
                "bucket_name": file_upload.bucket_name,
                "key": file_upload.key,
                "update": file_upload.update,
                "compressed": file_upload.compressed,
                "size": file_upload.size,
                "created_at": file_upload.created_at,
                "completed_at": file_upload.completed_at,
            }
        rows.append(
            {
                "id": download.id,
                "missing_symbol": {
                    "symbol": missing.symbol,
                    "debugid": missing.debugid,
                    "filename": missing.filename,
                    "code_file": missing.code_file,
                    "code_id": missing.code_id,
                    "count": missing.count,
                },
                "file_upload": file_upload,
                "created_at": download.created_at,
                "completed_at": download.completed_at,
                "error": download.error,
            }
        )

    context["microsoft_downloads"] = rows

    return http.JsonResponse(context)


def filter_microsoft_downloads(qs, form):
    qs = _filter_form_dates(qs, form, ("created_at", "modified_at"))
    for key in ("symbol", "debugid", "filename"):
        if form.cleaned_data[key]:
            qs = qs.filter(
                **{f"missing_symbol__{key}__contains": form.cleaned_data[key]}
            )
    if form.cleaned_data["state"] == "specific-error":
        specific_error = form.cleaned_data["error"]
        qs = qs.filter(error__icontains=specific_error)
    elif form.cleaned_data["state"] == "errored":
        qs = qs.filter(error__isnull=False)
    elif form.cleaned_data["state"] == "file-upload":
        qs = qs.filter(file_upload__isnull=False)
    elif form.cleaned_data["state"] == "no-file-upload":
        qs = qs.filter(file_upload__isnull=True)
    elif form.cleaned_data["state"]:  # pragma: no cover
        raise NotImplementedError(form.cleaned_data["state"])

    return qs
