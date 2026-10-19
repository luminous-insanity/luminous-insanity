# accounts/forms.py

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

# Username rules for NEW accounts. Change the numbers here and everything follows
# (the signup check, the box on the page, and the help text).
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20


class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=200, help_text='Required')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['username']
        # Django's own text says "150 characters or fewer", which is no longer true here.
        field.help_text = (
            f'{USERNAME_MIN_LENGTH} to {USERNAME_MAX_LENGTH} characters. '
            'Letters, numbers and @ . + - _ only.'
        )
        field.widget.attrs['maxlength'] = USERNAME_MAX_LENGTH   # stops typing past the limit

    def clean_username(self):
        username = self.cleaned_data.get('username', '')
        if not USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH:
            raise forms.ValidationError(
                f'Usernames must be {USERNAME_MIN_LENGTH} to {USERNAME_MAX_LENGTH} characters long.'
            )
        # "Dallas" and "dallas" would be two accounts that look the same on the leaderboard.
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is already taken.')
        return username


class LoginForm(AuthenticationForm):
    """
    Logging in only has to check a name and a password, so this form adds nothing.

    It used to cap usernames at 30 characters, while signup allowed 150, so anyone
    with a longer name could sign up and then never log in again. It also stripped
    spaces off passwords that signup had kept. Django's own form has neither problem.
    """
