# Mobile API patch — Google first-user fix + FCM push

Apply these files into your existing project’s `mobileapi/` folder (overwrite the four existing modules; add `push.py`).

## Files in this package

| File | Change |
|------|--------|
| `mobileapi/auth.py` | Fixes first-time Google sign-in (was 500 because User was never created) |
| `mobileapi/push.py` | **New** — Firebase Admin FCM sender (safe no-op if credentials missing) |
| `mobileapi/social.py` | Push on friend request + private whisper |
| `mobileapi/competitions.py` | Push on new challenge |
| `mobileapi/relay.py` | Push on Relay Wars next turn after pick/skip |

## Server setup (one-time)

1. Add to `requirements.txt`:
   ```
   firebase-admin==6.6.0
   ```
   Then install in the virtualenv.

2. In `GDP/settings.py` (or equivalent):
   ```python
   FIREBASE_ADMIN_CREDENTIALS = config('FIREBASE_ADMIN_CREDENTIALS', default='')
   ```

3. On the server only, in `.env`:
   ```
   FIREBASE_ADMIN_CREDENTIALS=/absolute/path/to/firebase-service-account.json
   ```
   Download the service-account JSON from Firebase Console → Project settings → Service accounts.  
   Keep it outside the public web root. Never commit it.

4. Restart the app (PythonAnywhere: reload the web app).

If `FIREBASE_ADMIN_CREDENTIALS` is empty or the file is missing, the site continues to work normally; push sending is a no-op. Local phone reminders do not depend on this.

## Google Sign-In note

Flutter must request an ID token for the same OAuth client ID configured as `GOOGLE_CLIENT_ID` on the server. Register the Android package `com.gamedaypicks.app` in Firebase and place `google-services.json` in the Flutter project’s `android/app/`.
