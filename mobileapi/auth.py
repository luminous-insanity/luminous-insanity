from .common import *
from .common import _tokens_for, _user_payload

class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        form = SignUpForm(request.data)
        if not form.is_valid():
            return Response({'errors': form.errors.get_json_data()}, status=status.HTTP_400_BAD_REQUEST)
        user = form.save()
        PlayerIdentity.objects.get_or_create(user=user)
        touch_activity(user)
        return Response({'user': _user_payload(user), **_tokens_for(user)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        identifier = str(request.data.get('identifier') or request.data.get('username') or request.data.get('email') or '').strip()
        password = request.data.get('password') or ''
        if not identifier or not password:
            return Response({'detail': 'Username/email and password are required.'}, status=400)
        user = authenticate(request, username=identifier, password=password)
        if user is None or not user.is_active:
            return Response({'detail': 'Invalid login credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
        touch_activity(user)
        return Response({'user': _user_payload(user), **_tokens_for(user)})


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        raw_token = request.data.get('id_token')
        if not raw_token:
            return Response({'detail': 'A Google ID token is required.'}, status=400)
        if not settings.GOOGLE_CLIENT_ID:
            return Response({'detail': 'Google sign-in is not configured on this server.'}, status=503)
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token
            claims = id_token.verify_oauth2_token(
                raw_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID,
            )
        except Exception:
            log.info('Rejected invalid Google ID token for mobile sign-in.', exc_info=True)
            return Response({'detail': 'Google sign-in could not be verified.'}, status=401)

        email = (claims.get('email') or '').strip().lower()
        subject = claims.get('sub')
        if not email or not subject or not claims.get('email_verified'):
            return Response({'detail': 'Google did not provide a verified email address.'}, status=401)

        from allauth.socialaccount.models import SocialAccount
        from allauth.account.models import EmailAddress
        with transaction.atomic():
            social = SocialAccount.objects.select_related('user').filter(provider='google', uid=subject).first()
            email_row = EmailAddress.objects.select_related('user').filter(email__iexact=email).first()
            if social:
                user = social.user
                if email_row and email_row.user_id != user.id:
                    return Response({'detail': 'This verified email is already associated with a different account.'}, status=409)
            elif email_row:
                user = email_row.user
            else:
                user = User.objects.filter(email__iexact=email).order_by('pk').first()
                if user is None:
                    base = ''.join(ch for ch in email.split('@', 1)[0] if ch.isalnum() or ch in '._+-')[:20] or 'player'
                    if len(base) < 3:
                        base = f'player{base}'[:20]
                    username = base
                    suffix = 1
                    while User.objects.filter(username__iexact=username).exists():
                        tail = str(suffix)
                        username = f'{base[:20-len(tail)]}{tail}'
                        suffix += 1
            if not user.is_active:
                return Response({'detail': 'This account is inactive.'}, status=403)
            existing_social = SocialAccount.objects.filter(provider='google', user=user).first()
            if existing_social and existing_social.uid != subject:
                return Response({'detail': 'This account is already linked to a different Google account.'}, status=409)
            if not social:
                SocialAccount.objects.get_or_create(
                    provider='google', uid=subject,
                    defaults={'user': user, 'extra_data': dict(claims)},
                )
            email_row, _ = EmailAddress.objects.get_or_create(
                user=user, email=email,
                defaults={'verified': True, 'primary': not EmailAddress.objects.filter(user=user, primary=True).exists()},
            )
            if not email_row.verified:
                email_row.verified = True
                email_row.save(update_fields=['verified'])
            PlayerIdentity.objects.get_or_create(user=user)
            touch_activity(user)
        return Response({'user': _user_payload(user), **_tokens_for(user)})


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=401)
        return Response(serializer.validated_data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.data.get('refresh')
        if not raw:
            return Response({'detail': 'Refresh token is required.'}, status=400)
        try:
            token = RefreshToken(raw)
            if str(token.get('user_id')) != str(request.user.pk):
                return Response({'detail': 'That refresh token does not belong to this account.'}, status=403)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Refresh token is invalid or expired.'}, status=400)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'user': _user_payload(request.user)})

    def patch(self, request):
        identity, _ = PlayerIdentity.objects.get_or_create(user=request.user)
        update_fields = []
        if 'favorite_team' in request.data:
            team = str(request.data.get('favorite_team') or '').upper()
            if team and team not in TEAM_DATA:
                return Response({'detail': 'Choose a valid NFL team abbreviation.'}, status=400)
            new_season = identity.division_season != settings.NFL_SEASON
            identity.favorite_team = team
            update_fields.append('favorite_team')
            # Match the website: division is assigned on first selection and
            # remains locked for the rest of the configured season.
            if team and (new_season or not identity.division):
                identity.division = team_division(team)
                identity.division_season = settings.NFL_SEASON
                update_fields.extend(['division', 'division_season'])
            elif not team and new_season:
                identity.division = ''
                identity.division_season = None
                update_fields.extend(['division', 'division_season'])
        if 'active_title' in request.data:
            from accounts.titles import available_titles
            title = str(request.data.get('active_title') or '')
            if title and title not in available_titles(request.user):
                return Response({'detail': 'That title has not been unlocked.'}, status=400)
            identity.active_title = title
            update_fields.append('active_title')
        if update_fields:
            identity.save(update_fields=update_fields + ['updated_at'])
        return Response({'user': _user_payload(request.user)})


