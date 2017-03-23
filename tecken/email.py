# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import boto3
from django.conf import settings

ses = boto3.client('ses', region_name=settings.AWS_CONFIG['AWS_REGION'])


def send_email(to, subject, body, cc=None):
    if isinstance(to, str):
        to = [to]
    if cc is None:
        cc = []
    elif isinstance(cc, str):
        cc = [cc]
    return ses.send_email(
        Source=settings.AWS_CONFIG['EMAIL_SOURCE'],
        Destination={
            'ToAddresses': to,
            'CcAddresses': cc,
        },
        Message={
            'Subject': {'Data': subject, 'Charset': 'UTF-8'},
            'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}}
        }
    )['MessageId']
