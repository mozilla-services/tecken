# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import uuid
from collections import OrderedDict

from django import forms

from .cache import CachedFileCache
from .fields import CachedFileField
from .widgets import CachedFileHiddenInput


class AutoClassFormMixin:
    """
    A form mixin that adds the 'form-control' to all field widgets
    automatically
    """
    class_names = {
        'form-control': {
            'excluded_widgets': ['file'],
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in list(self.fields.values()):
            classes = field.widget.attrs.get('class', '').split(' ')
            for class_name, options in list(self.class_names.items()):
                if class_name in classes:
                    continue
                excluded_widgets = options.get('excluded_widgets', [])
                if (hasattr(field.widget, 'input_type') and
                        field.widget.input_type in excluded_widgets):
                    continue
                field.widget.attrs['class'] = ' '.join([class_name] + classes)


class CreatedByModelFormMixin(forms.ModelForm):
    """
    Custom Django form mixin that takes a user object and if the provided
    model form instance has a primary key checks if the given user
    matches the 'created_by' field.
    """
    def __init__(self, user, *args, **kwargs):
        self.created_by = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        # create the object without committing, since we haven't
        # set the required created_by field yet
        obj = super().save(commit=False)

        # set the field to the user that created the object
        obj.created_by = self.created_by

        if commit:
            # actually start the real object, and return the model object
            obj.save()
        return obj

    def clean(self):
        """
        only allow deleting clusters that one created
        """
        super().clean()
        if self.instance.id and self.created_by != self.instance.created_by:
            raise forms.ValidationError(
                'Access denied to the data of another user'
            )


class CachedFileModelFormMixin(forms.ModelForm):
    """
    A model form mixin that automatically adds additional hidden form fields
    to store a random value to be used as the cache key for caching FileField
    files on submission. That is needed to prevent having to reselect files
    over and over again when form submission fails for the fields other than
    the file fields.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = CachedFileCache()
        self.cached_filefields = OrderedDict()
        self.required_filefields = []

        field_order = []
        for name, field in list(self.fields.items()):
            # add any found field to the list of order items
            field_order.append(name)

            # in case it's a file input
            if isinstance(field, CachedFileField):
                # we'll use this later in the clean and save step
                self.cached_filefields[name] = field

                # store the field that are required so we can validate
                # them optionally in our clean method
                if field.real_required:
                    self.required_filefields.append(name)

                # get the name of the cache key field
                cachekey_input_name = self.cachekey_input_name(name)
                field_order.append(cachekey_input_name)

                # add the cache key field
                self.fields[cachekey_input_name] = forms.CharField(
                    max_length=32,
                    widget=CachedFileHiddenInput(),
                    initial=uuid.uuid4().hex
                )

        self.order_fields(field_order)

    def cachekey_input_name(self, name):
        return name + '-cache'

    def cachekey_input_data(self, field):
        name = self.cachekey_input_name(field)
        return self.cleaned_data[name]

    def save(self, *args, **kwargs):
        # on save get rid of the cache keys
        for name in self.cached_filefields:
            self.cache.remove(self.cachekey_input_data(name))
        return super().save(*args, **kwargs)

    def clean(self):
        for field_name in self.cached_filefields:
            # get the name of the cache key field name and its value
            cache_key = self.cachekey_input_data(field_name)

            # check form data if the file field was submitted
            submitted_file = self.cleaned_data.get(field_name)
            if submitted_file is None:
                # if not, check the cache and update the cleaned data
                cached_file = self.cache.retrieve(cache_key, field_name)
                if cached_file is None:
                    # raise a required validation error if nothing was found
                    if field_name in self.required_filefields:
                        field = self.cached_filefields[field_name]
                        self.add_error(
                            field_name,
                            forms.ValidationError(
                                field.error_messages['required'],
                                code='required'
                            )
                        )
                else:
                    self.cleaned_data[field_name] = cached_file
            else:
                # or store the submitted file for later use (or reset after saving)
                self.cache.store(cache_key, submitted_file)
