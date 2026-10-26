# Tests for the dashboard's "Invite a Friend" button.
#   python manage.py test accounts.test_invite
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


class InviteAFriendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "a@example.com", "pw-12345-xyz")
        self.client.force_login(self.user)

    def test_dashboard_offers_invite_options(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Invite a Friend")
        self.assertContains(response, "Text Message")
        self.assertContains(response, "Email")
        self.assertContains(response, "WhatsApp")
        self.assertContains(response, "Copy Invite")

    def test_invite_link_goes_to_the_signup_page(self):
        response = self.client.get(reverse("dashboard"))
        self.assertTrue(response.context["invite_url"].endswith(reverse("signup")))
        self.assertTrue(response.context["invite_url"].startswith("http"))
        self.assertIn("alice invited you", response.context["invite_message"])
        self.assertIn(response.context["invite_url"], response.context["invite_message"])

    @override_settings(SITE_URL="https://gamedaypicks.example.com/")
    def test_site_url_setting_overrides_the_host(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(
            response.context["invite_url"],
            "https://gamedaypicks.example.com" + reverse("signup"),
        )

    def test_username_is_safely_escaped(self):
        evil = User.objects.create_user("x\"onmouseover=1", "e@example.com", "pw-12345-xyz")
        self.client.force_login(evil)
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, 'data-text="x"onmouseover')

    def test_friend_search_and_requests_tab_still_work(self):
        response = self.client.get(reverse("dashboard"), {"friend_search": "ali"})
        self.assertContains(response, "friend-search-form")
        self.assertContains(response, "friendsTabRequests")
