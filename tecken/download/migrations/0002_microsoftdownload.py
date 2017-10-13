# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-10-13 20:21
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0013_upload_content_hash'),
        ('download', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MicrosoftDownload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=500)),
                ('error', models.TextField(null=True)),
                ('skipped', models.NullBooleanField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(null=True)),
                ('file_upload', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='upload.FileUpload')),
                ('missing_symbol', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='download.MissingSymbol')),
            ],
        ),
    ]
