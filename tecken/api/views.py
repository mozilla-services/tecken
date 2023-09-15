# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
import logging
import time

import markus

from django import http
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import Permission
from django.db.models import Aggregate, Count, Q, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, BadRequest

from tecken.api import forms
from tecken.base.decorators import (
    api_login_required,
    api_permission_required,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.base.form_utils import filter_form_dates, ORM_OPERATORS, PaginationForm
from tecken.storage import StorageBucket
from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.upload.views import get_upload_bucket_urls

logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


# Arbitrary big number for paging so we don't do a count on the full table; this
# needs to match the big number used in the frontend
BIG_NUMBER = 1_000_000


class SumCardinality(Aggregate):
    template = "SUM(CARDINALITY(%(expressions)s))"


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
    seen = set()
    for url in get_upload_bucket_urls():
        bucket_info = StorageBucket(url)

        if bucket_info.name in seen:
            continue
        seen.add(bucket_info.name)
        context["urls"].append(
            {
                "url": url,
                "bucket_name": bucket_info.name,
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

    all_permissions = [
        Permission.objects.get(codename="upload_symbols"),
        Permission.objects.get(codename="upload_try_symbols"),
        Permission.objects.get(codename="view_all_uploads"),
        Permission.objects.get(codename="manage_tokens"),
    ]
    all_user_permissions = request.user.get_all_permissions()
    possible_permissions = [
        x
        for x in all_permissions
        if (
            f"{x.content_type.model}.{x.codename}" in all_user_permissions
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


def _uploads_content(form, pagination_form, qs, can_view_all):
    content = {"can_view_all": can_view_all}
    batch_size = settings.API_UPLOADS_BATCH_SIZE

    page = pagination_form.cleaned_data["page"]
    start = (page - 1) * batch_size
    end = start + batch_size + 1
    has_next = False

    if form.cleaned_data.get("order_by"):
        order_by = form.cleaned_data["order_by"]
    else:
        order_by = {"sort": "created_at", "reverse": True}

    rows = []
    order_by_string = ("-" if order_by["reverse"] else "") + order_by["sort"]
    uploads = qs.select_related("user").order_by(order_by_string)[start:end]
    for i, upload in enumerate(uploads):
        if i == batch_size:
            has_next = True
            break

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

    content["uploads"] = rows
    content["batch_size"] = batch_size
    content["order_by"] = order_by
    content["has_next"] = has_next

    # NOTE(willkg): This is the only way I could figure out to determine whether a
    # queryset had filters applied to it. We check that and if there are filters, we do
    # the count and if there are not filters, then we use BIG_NUMBER so we don't have to
    # do a row count in the postgres table of the entire table.
    if qs._has_filters().__dict__["children"]:
        content["total"] = qs.count()
    else:
        content["total"] = BIG_NUMBER

    return content


@metrics.timer_decorator("api", tags=["endpoint:uploads"])
@api_login_required
def uploads(request):
    form = forms.UploadsForm(request.GET, valid_sorts=("size", "created_at"))
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    pagination_form = PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    can_view_all = request.user.has_perm("upload.view_all_uploads")
    qs = Upload.objects.all()
    qs = filter_uploads(qs, can_view_all, request.user, form)

    context = _uploads_content(form, pagination_form, qs, can_view_all)
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
    qs = filter_form_dates(qs, form, ("created_at", "completed_at"))
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


def _upload_files_build_qs(request):
    form = forms.FileUploadsForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)
    qs = FileUpload.objects.all()
    for operator, value in form.cleaned_data["size"]:
        orm_operator = "size__{}".format(ORM_OPERATORS[operator])
        qs = qs.filter(**{orm_operator: value})
    qs = filter_form_dates(qs, form, ("created_at", "completed_at"))
    if form.cleaned_data.get("key"):
        key_q = Q(key__icontains=form.cleaned_data["key"][0])
        for other in form.cleaned_data["key"][1:]:
            key_q &= Q(key__icontains=other)
        qs = qs.filter(key_q)
    include_bucket_names = []
    for operator, bucket_name in form.cleaned_data["bucket_name"]:
        if operator == "!":
            qs = qs.exclude(bucket_name=bucket_name)
        else:
            include_bucket_names.append(bucket_name)
    if include_bucket_names:
        qs = qs.filter(bucket_name__in=include_bucket_names)
    return qs


def _upload_files_content(request, qs):
    pagination_form = PaginationForm(request.GET)
    if not pagination_form.is_valid():
        raise BadRequest("formerrors", pagination_form.errors)
    page = pagination_form.cleaned_data["page"]

    files = []
    batch_size = settings.API_FILES_BATCH_SIZE
    start = (page - 1) * batch_size
    end = start + batch_size + 1
    has_next = False

    upload_ids = set()
    file_uploads = qs.order_by("-created_at")[start:end]
    for i, file_upload in enumerate(file_uploads):
        if i == batch_size:
            has_next = True
            break

        files.append(
            {
                "id": file_upload.id,
                "key": file_upload.key,
                "update": file_upload.update,
                "compressed": file_upload.compressed,
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

    content = {
        "files": files,
        "has_next": has_next,
        "batch_size": batch_size,
    }

    # NOTE(willkg): This is the only way I could figure out to determine whether a
    # queryset had filters applied to it. We check that and if there are filters, we do
    # the count and if there are not filters, then we use BIG_NUMBER so we don't have to
    # do a row count in the postgres table of the entire table.
    if qs._has_filters().__dict__["children"]:
        content["total"] = qs.count()
    else:
        content["total"] = BIG_NUMBER

    return content


@metrics.timer_decorator("api", tags=["endpoint:upload_files"])
@api_login_required
@api_permission_required("upload.view_all_uploads")
def upload_files(request):
    qs = _upload_files_build_qs(request)
    if isinstance(qs, http.JsonResponse):
        return qs
    try:
        context = _upload_files_content(request, qs)
    except BadRequest as e:
        return http.JsonResponse({"errors": e.args[1]}, status=400)

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
        "debug_filename": file_upload.debug_filename,
        "debug_id": file_upload.debug_id,
        "code_file": file_upload.code_file,
        "code_id": file_upload.code_id,
        "generator": file_upload.generator,
        "upload": None,
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

    with metrics.timer("api_stats", tags=["section:all_uploads"]):
        upload_qs = Upload.objects.all()

        if not all_uploads:
            upload_qs = upload_qs.filter(user=request.user)

        def count_and_size(qs, start, end):
            sub_qs = qs.filter(created_at__gte=start, created_at__lt=end)
            return sub_qs.aggregate(count=Count("id"), total_size=Sum("size"))

        numbers["uploads"] = {
            "all_uploads": all_uploads,
            "today": count_and_size(upload_qs, start_today, today),
            "yesterday": count_and_size(upload_qs, start_yesterday, start_today),
            "last_30_days": count_and_size(upload_qs, last_30_days, today),
        }

    # When doing aggregates on rows that don't exist you can get a None instead of 0.
    # Only really happens in cases where you have extremely little in the database.
    def nones_to_zero(obj):
        for key, value in obj.items():
            if isinstance(value, dict):
                nones_to_zero(value)
            elif value is None:
                obj[key] = 0

    nones_to_zero(numbers)

    context = {"stats": numbers}
    return http.JsonResponse(context)


@metrics.timer_decorator("codeinfo_test")
@api_require_http_methods(["GET"])
@set_cors_headers(origin="*", methods="GET")
def syminfo(request, somefile, someid):
    start_time = time.time()
    ret = FileUpload.objects.lookup_by_syminfo(some_file=somefile, some_id=someid)
    end_time = time.time()
    if ret:
        sym_file = ret["debug_filename"]
        if sym_file.endswith(".pdb"):
            sym_file = sym_file[:-4] + ".sym"

        new_url = request.build_absolute_uri(
            reverse(
                "download:download_symbol",
                args=(ret["debug_filename"], ret["debug_id"], sym_file),
            )
        )

        return http.JsonResponse(
            {
                "debug_id": ret["debug_id"],
                "debug_filename": ret["debug_filename"],
                "code_file": ret["code_file"],
                "code_id": ret["code_id"],
                "generator": ret["generator"],
                "url": new_url,
                "time": end_time - start_time,
            }
        )

    return http.HttpResponseNotFound("Code file / id Not Found")
