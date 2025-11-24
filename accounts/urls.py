from django.urls import path
from .views import (
    CustomLoginView, SignupView, PhoneVerifyView, custom_logout,
    ProfileOverviewView, ProfileSettingsView, ProfileSecurityView,
    ProfileActivityView, ProfileBillingView, ProfileStatementsView,
    ProfileReferralsView, ProfileApiKeysView, ProfileLogsView, ProfilePropertiesView
)

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        CustomLoginView.as_view(),
        name="login",
    ),
    path("logout/", custom_logout, name="logout"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("phone-verify/", PhoneVerifyView.as_view(), name="phone_verify"),

    # Profile URLs
    path("profile/", ProfileOverviewView.as_view(), name="profile_overview"),
    path("profile/settings/", ProfileSettingsView.as_view(), name="profile_settings"),
    path("profile/security/", ProfileSecurityView.as_view(), name="profile_security"),
    path("profile/activity/", ProfileActivityView.as_view(), name="profile_activity"),
    path("profile/billing/", ProfileBillingView.as_view(), name="profile_billing"),
    path("profile/statements/", ProfileStatementsView.as_view(), name="profile_statements"),
    path("profile/referrals/", ProfileReferralsView.as_view(), name="profile_referrals"),
    path("profile/api-keys/", ProfileApiKeysView.as_view(), name="profile_api_keys"),
    path("profile/logs/", ProfileLogsView.as_view(), name="profile_logs"),
    path("profile/properties/", ProfilePropertiesView.as_view(), name="profile_properties"),
]
