from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from restaurants.models import MenuItem, Restaurant

from .cart import MAX_QUANTITY
from .models import Order


class CravioFlowTests(TestCase):
    def setUp(self):
        self.vendor = User.objects.create_user("vendor1", password="pass12345!", role=User.Role.VENDOR)
        self.other_vendor = User.objects.create_user("vendor2", password="pass12345!", role=User.Role.VENDOR)
        self.customer = User.objects.create_user("cust1", password="pass12345!", role=User.Role.CUSTOMER)
        self.admin = User.objects.create_superuser("boss", password="pass12345!")
        # Both in Koramangala, Bengaluru, delivering within 6 km.
        self.restaurant = Restaurant.objects.create(owner=self.vendor, name="Spice Hub", area="koramangala")
        self.other_restaurant = Restaurant.objects.create(owner=self.other_vendor, name="Pasta Place", area="koramangala")
        self.item = MenuItem.objects.create(restaurant=self.restaurant, name="Paneer Tikka", price=Decimal("150.00"))

    # ---- role based redirects ----
    def test_login_redirects_each_role_to_its_dashboard(self):
        expected = {
            "cust1": reverse("restaurants:list"),
            "vendor1": reverse("restaurants:vendor_dashboard"),
            "boss": reverse("accounts:admin_dashboard"),
        }
        for username, url in expected.items():
            self.client.logout()
            response = self.client.post(reverse("accounts:login"), {"username": username, "password": "pass12345!"})
            self.assertRedirects(response, url, fetch_redirect_response=False)

    # ---- RBAC ----
    def test_customer_cannot_open_vendor_or_admin_pages(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("restaurants:vendor_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:admin_dashboard")).status_code, 403)

    def test_vendor_cannot_open_admin_dashboard(self):
        self.client.force_login(self.vendor)
        self.assertEqual(self.client.get(reverse("accounts:admin_dashboard")).status_code, 403)

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(reverse("restaurants:vendor_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    # ---- vendor menu management ----
    def test_vendor_can_add_edit_delete_items(self):
        self.client.force_login(self.vendor)
        self.client.post(reverse("restaurants:item_create"), {"name": "Naan", "price": "30", "is_available": "on"})
        naan = MenuItem.objects.get(name="Naan")
        self.client.post(reverse("restaurants:item_edit", args=[naan.pk]), {"name": "Butter Naan", "price": "40", "is_available": "on"})
        naan.refresh_from_db()
        self.assertEqual(naan.name, "Butter Naan")
        self.client.post(reverse("restaurants:item_delete", args=[naan.pk]))
        self.assertFalse(MenuItem.objects.filter(pk=naan.pk).exists())

    def test_vendor_cannot_edit_another_vendors_item(self):
        self.client.force_login(self.other_vendor)
        response = self.client.post(reverse("restaurants:item_edit", args=[self.item.pk]), {"name": "Hacked", "price": "1"})
        self.assertEqual(response.status_code, 404)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Paneer Tikka")

    def _deliver_to(self, area):
        self.client.post(reverse("restaurants:set_location"), {"area": area})

    # ---- cart, checkout, simulated payment ----
    def test_full_order_flow_without_razorpay_keys(self):
        self.client.force_login(self.customer)
        self._deliver_to("indiranagar")  # about 4 km away
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.client.post(reverse("orders:add", args=[self.item.pk]))

        response = self.client.post(reverse("orders:checkout"))
        order = Order.objects.get()
        self.assertRedirects(response, reverse("orders:pay", args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(order.total, Decimal("300.00"))
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(order.lines.get().quantity, 2)

        self.client.post(reverse("orders:callback", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_vendor_cannot_mark_an_unpaid_order_as_paid(self):
        order = Order.objects.create(customer=self.customer, restaurant=self.restaurant, total=Decimal("150"))
        self.client.force_login(self.vendor)
        for status in ["paid", "preparing", "delivered"]:
            self.client.post(reverse("restaurants:order_status", args=[order.pk]), {"status": status})
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)

    def test_vendor_cannot_send_a_paid_order_back_to_pending(self):
        order = Order.objects.create(customer=self.customer, restaurant=self.restaurant, total=Decimal("150"), status=Order.Status.PAID)
        self.client.force_login(self.vendor)
        self.client.post(reverse("restaurants:order_status", args=[order.pk]), {"status": "pending_payment"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_vendor_can_update_status_only_for_own_orders(self):
        order = Order.objects.create(customer=self.customer, restaurant=self.restaurant, total=Decimal("150"), status=Order.Status.PAID)
        self.client.force_login(self.other_vendor)
        self.assertEqual(self.client.post(reverse("restaurants:order_status", args=[order.pk]), {"status": "paid"}).status_code, 404)
        self.client.force_login(self.vendor)
        self.client.post(reverse("restaurants:order_status", args=[order.pk]), {"status": "preparing"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)

    # ---- delivery range ----
    def test_checkout_needs_a_delivery_location(self):
        self.client.force_login(self.customer)
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        response = self.client.post(reverse("orders:checkout"), follow=True)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "Set your delivery location before checking out.")

    def test_checkout_is_refused_when_the_restaurant_is_out_of_range(self):
        self.client.force_login(self.customer)
        self._deliver_to("indiranagar")
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self._deliver_to("whitefield")  # about 13 km away: moved after filling the cart
        response = self.client.post(reverse("orders:checkout"), follow=True)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "Spice Hub does not deliver to Whitefield, Bengaluru.")

    def test_cannot_add_dishes_from_a_restaurant_that_does_not_deliver_to_you(self):
        self._deliver_to("fort-road")  # Kannur, hundreds of kilometres away
        response = self.client.post(reverse("orders:add", args=[self.item.pk]), follow=True)
        self.assertEqual(self._cart(), {})
        self.assertContains(response, "does not deliver to Fort Road, Kannur")

    def test_cart_shows_distance_and_delivery_time(self):
        self._deliver_to("indiranagar")
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        response = self.client.get(reverse("orders:cart"))
        self.assertTrue(response.context["in_range"])
        self.assertContains(response, "To <b>Indiranagar, Bengaluru</b>")
        self.assertContains(response, "arrives in")

    def test_empty_cart_cannot_checkout(self):
        self.client.force_login(self.customer)
        self.client.post(reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)

    # ---- cart quantity buttons ----
    def _cart(self):
        return self.client.session.get("cart", {"items": {}})["items"]

    def test_plus_and_minus_change_the_quantity_and_zero_removes_the_item(self):
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "inc"})
        self.assertEqual(self._cart()[str(self.item.pk)], 2)

        self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "dec"})
        self.assertEqual(self._cart()[str(self.item.pk)], 1)

        self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "dec"})
        self.assertEqual(self._cart(), {})
        self.assertIsNone(self.client.session["cart"]["restaurant"])

    def test_quantity_is_capped(self):
        for _ in range(MAX_QUANTITY + 5):
            self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.assertEqual(self._cart()[str(self.item.pk)], MAX_QUANTITY)
        self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "inc"})
        self.assertEqual(self._cart()[str(self.item.pk)], MAX_QUANTITY)

    def test_updating_an_item_that_is_not_in_the_cart_does_nothing(self):
        response = self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "inc"})
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertEqual(self._cart(), {})

    def test_update_returns_to_the_page_it_came_from_but_never_to_another_site(self):
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        menu = reverse("restaurants:detail", args=[self.restaurant.pk])

        response = self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "inc", "next": menu})
        self.assertRedirects(response, menu, fetch_redirect_response=False)

        response = self.client.post(reverse("orders:update", args=[self.item.pk]), {"action": "inc", "next": "https://evil.example/steal"})
        self.assertRedirects(response, reverse("orders:cart"), fetch_redirect_response=False)

    def test_adding_from_another_restaurant_starts_a_new_cart(self):
        other_item = MenuItem.objects.create(restaurant=self.other_restaurant, name="Penne", price=Decimal("260.00"))
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.client.post(reverse("orders:add", args=[other_item.pk]))
        self.assertEqual(self._cart(), {str(other_item.pk): 1})

    # ---- pages ----
    def test_cart_page_shows_lines_and_total(self):
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        response = self.client.get(reverse("orders:cart"))
        self.assertContains(response, "Paneer Tikka")
        self.assertContains(response, "₹300")
        self.assertContains(response, "Log in to check out")

    def test_order_history_shows_progress(self):
        order = Order.objects.create(customer=self.customer, restaurant=self.restaurant, total=Decimal("150"), status=Order.Status.PREPARING)
        self.assertEqual(order.progress_step, 2)
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders:history"))
        self.assertContains(response, "Order progress: Preparing")
        self.assertContains(response, "₹150")

    def test_pay_page_explains_simulated_payment_without_keys(self):
        self.client.force_login(self.customer)
        self._deliver_to("koramangala")
        self.client.post(reverse("orders:add", args=[self.item.pk]))
        self.client.post(reverse("orders:checkout"))
        response = self.client.get(reverse("orders:pay", args=[Order.objects.get().pk]))
        self.assertContains(response, "Simulate payment")
        self.assertContains(response, "1 × Paneer Tikka")
