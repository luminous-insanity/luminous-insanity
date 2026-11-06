
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('mobileapi.urls')),
    path('api/', include('api.urls')),  # Existing cron sync endpoint remains unchanged.
    path('relay-wars/', include('relaywars.urls')),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),
    path('', include('main.urls')),
]
