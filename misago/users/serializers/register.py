from rest_framework import serializers

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import six
from django.utils.translation import ugettext as _

from misago.users import captcha, validators
from misago.users.bans import get_email_ban, get_username_ban


UserModel = get_user_model()


class BaseRegisterUserSerializer(serializers.Serializer):
    username = serializers.CharField(
        max_length=255,
        validators=[validators.validate_username],
    )
    email = serializers.CharField(
        max_length=255,
        validators=[validators.validate_email],
    )

    def validate_username(self, data):
        ban = get_username_ban(data, registration_only=True)
        if ban:
            if ban.user_message:
                raise ValidationError(ban.user_message)
            else:
                raise ValidationError(_("This usernane is not allowed."))
        return data

    def validate_email(self, data):
        ban = get_email_ban(data, registration_only=True)
        if ban:
            if ban.user_message:
                raise ValidationError(ban.user_message)
            else:
                raise ValidationError(_("This e-mail address is not allowed."))
        return data

    def validate_added_errors(self):
        if self._added_errors:
            # fail registration with additional errors
            raise serializers.ValidationError(self._added_errors)
            
    def validate(self, data):
        self._added_errors = {}
        return data

    def add_error(self, field, error):
        """
        custom implementation for quasi add_error feature for custom validators
        we are doing some hacky introspection here to deconstruct ValidationError
        """
        self._added_errors.setdefault(field, [])

        if isinstance(error, ValidationError):
            self._added_errors[field].extend(list(error))
        elif isinstance(error, serializers.ValidationError):
            details = [e['message'] for e in error.get_full_details()]
            self._added_errors[field].extend(details)
        else:
            self._added_errors[field].append(six.text_type(error))


class SocialRegisterUserSerializer(BaseRegisterUserSerializer):
    def validate(self, data):
        data = super(SocialRegisterUserSerializer, self).validate(data)

        request = self.context['request']

        validators.validate_new_registration(request, data, self.add_error)

        self.validate_added_errors()

        return data


class RegisterUserSerializer(BaseRegisterUserSerializer):
    password = serializers.CharField(
        max_length=255,
        trim_whitespace=False,
    )

    def validate(self, data):
        data = super(RegisterUserSerializer, self).validate(data)

        request = self.context['request']

        try:
            self.full_clean_password(data)
        except ValidationError as e:
            self.add_error('password', e)

        validators.validate_new_registration(request, data, self.add_error)

        self.validate_added_errors()

        # run test for captcha
        try:
            captcha.test_request(self.context['request'])
        except ValidationError as e:
            raise serializers.ValidationError({'captcha': e.message})

        return data

    def full_clean_password(self, data):
        if data.get('password'):
            validate_password(
                data['password'],
                user=UserModel(
                    username=data.get('username'),
                    email=data.get('email'),
                ),
            )
