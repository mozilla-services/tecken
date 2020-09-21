# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""Form-related utilities"""

import datetime


ORM_OPERATORS = {"<=": "lte", ">=": "gte", "=": "exact", "<": "lt", ">": "gt"}


def filter_form_dates(qs, form, keys):
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
                    # datetimes are passed back end forth in XHR, the datetimes
                    # are converted with isoformat() which drops microseconds.
                    # Therefore add 1 second to avoid matching the latest date.
                    value += datetime.timedelta(seconds=1)
                orm_operator = "{}__{}".format(key, ORM_OPERATORS[operator])
                qs = qs.filter(**{orm_operator: value})
    return qs
