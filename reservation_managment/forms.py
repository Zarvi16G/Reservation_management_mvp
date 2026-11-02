from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class SignupForm(UserCreationForm):
    """
    Public sign-up, for customers only.

    A ModelForm only reads the fields listed in Meta.fields from the POST data,
    so extra fields such as `is_staff=on` or `is_superuser=on` are ignored.
    Staff accounts are created by the superuser in the admin.
    """

    email = forms.EmailField(
        label=_('Email'),
        help_text=_('Booking confirmations are sent here.'),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone')

    def clean_email(self):
        return self.cleaned_data['email'].lower()  # Unique: checked by the model (User.email).


class ProfileForm(forms.ModelForm):
    """
    The logged-in user's own details. Changing the email needs the current
    password: with an open session alone, nobody can take over the account
    (the email is where password reset links are sent).
    """

    current_password = forms.CharField(
        label=_('Current password'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
        required=False,
        help_text=_('Only needed to change your email.'),
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone', 'language')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved_email = self.instance.email  # Before the form changes the instance.

    def clean_email(self):
        return self.cleaned_data['email'].lower()  # Unique: checked by the model (User.email).

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        if email and email != self.saved_email.lower():
            password = cleaned_data.get('current_password')
            if not password:
                self.add_error(
                    'current_password', _('Enter your current password to change your email.')
                )
            elif not self.instance.check_password(password):
                self.add_error('current_password', _('The password is not correct.'))
        return cleaned_data
