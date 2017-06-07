# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-06-02 19:58
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FileUpload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bucket_name', models.CharField(max_length=100)),
                ('key', models.CharField(max_length=300)),
                ('update', models.BooleanField(default=False)),
                ('compressed', models.BooleanField(default=False)),
                ('size', models.PositiveIntegerField()),
                ('completed_at', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Upload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(max_length=100)),
                ('bucket_name', models.CharField(max_length=100)),
                ('bucket_region', models.CharField(max_length=100, null=True)),
                ('bucket_endpoint_url', models.CharField(max_length=100, null=True)),
                ('inbox_key', models.CharField(max_length=300)),
                ('completed_at', models.DateTimeField(null=True)),
                ('size', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='fileupload',
            name='upload',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='upload.Upload'),
        ),
    ]
