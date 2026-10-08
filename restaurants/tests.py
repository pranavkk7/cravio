from decimal import Decimal

from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from orders.models import Order, OrderLine

from . import location
from .models import MenuItem, Restaurant
from .templatetags.cravio_extras import cover, initial, inr, km


class TemplateFilterTests(TestCase):
    def test_inr_uses_indian_digit_grouping(self):
        self.assertEqual(inr(Decimal("150.00")), "₹150")
        self.assertEqual(inr(Decimal("1500")), "₹1,500")
        self.assertEqual(inr(125000), "₹1,25,000")
        self.assertEqual(inr(Decimal("12345678.50")), "₹1,23,45,678.50")
        self.assertEqual(inr(Decimal("99.5")), "₹99.50")
        self.assertEqual(inr(0), "₹0")
        self.assertEqual(inr(Decimal("-250")), "-₹250")

    def test_inr_ignores_values_that_are_not_numbers(self):
        self.assertEqual(inr(None), "")
        self.assertEqual(inr("abc"), "")

    def test_cover_is_stable_and_always_a_known_style(self):
        self.assertEqual(cover(7), cover(7))
        self.assertIn(cover(123), {f"cover-{n}" for n in range(1, 7)})
        self.assertEqual(cover("not a number"), "cover-1")

    def test_km_is_friendly(self):
        self.assertEqual(km(0.45), "450 m")
        self.assertEqual(km(0.998), "1.0 km")
        self.assertEqual(km(3.24), "3.2 km")
        self.assertEqual(km(27.6), "28 km")
        self.assertEqual(km(None), "")

    def test_initial(self):
        self.assertEqual(initial("spice hub"), "S")
        self.assertEqual(initial(""), "?")


class RestaurantPagesTests(TestCase):
    def setUp(self):
        self.vendor = User.objects.create_user("vendor1", password="pass12345!", role=User.Role.VENDOR)
        self.vendor2 = User.objects.create_user("vendor2", password="pass12345!", role=User.Role.VENDOR)
        self.customer = User.objects.create_user("cust1", password="pass12345!", role=User.Role.CUSTOMER)
        self.admin = User.objects.create_superuser("boss", password="pass12345!")

        self.spice = Restaurant.objects.create(owner=self.vendor, name="Spice Hub", description="North Indian favourites")
        self.pasta = Restaurant.objects.create(owner=self.vendor2, name="Pasta Place", description="Italian comfort food")
        self.tikka = MenuItem.objects.create(restaurant=self.spice, name="Paneer Tikka", price=Decimal("150.00"))
        MenuItem.objects.create(restaurant=self.spice, name="Butter Naan", price=Decimal("45.00"))
        MenuItem.objects.create(restaurant=self.spice, name="Secret Special", price=Decimal("20.00"), is_available=False)
        MenuItem.objects.create(restaurant=self.pasta, name="Penne Arrabbiata", price=Decimal("260.00"))

    # ---- home page ----
    def test_home_lists_open_restaurants_with_dish_count_and_lowest_price(self):
        response = self.client.get(reverse("restaurants:list"))
        self.assertContains(response, "Spice Hub")
        self.assertContains(response, "Pasta Place")

        spice = next(r for r in response.context["restaurants"] if r.pk == self.spice.pk)
        self.assertEqual(spice.item_count, 2)  # the unavailable dish is not counted
        self.assertEqual(spice.min_price, Decimal("45.00"))
        self.assertContains(response, "From ₹45")

    def test_closed_restaurants_are_hidden(self):
        self.pasta.is_open = False
        self.pasta.save()
        response = self.client.get(reverse("restaurants:list"))
        self.assertNotContains(response, "Pasta Place")

    def test_search_matches_restaurant_name_description_and_dish(self):
        def names(query):
            response = self.client.get(reverse("restaurants:list"), {"q": query})
            return [r.name for r in response.context["restaurants"]]

        self.assertEqual(names("spice"), ["Spice Hub"])  # name
        self.assertEqual(names("italian"), ["Pasta Place"])  # description
        self.assertEqual(names("naan"), ["Spice Hub"])  # dish
        self.assertEqual(names("secret"), [])  # unavailable dishes do not match
        self.assertEqual(names("zzz"), [])

    def test_search_keeps_dish_counts_correct(self):
        response = self.client.get(reverse("restaurants:list"), {"q": "naan"})
        self.assertEqual(response.context["restaurants"][0].item_count, 2)

    def test_empty_search_result_shows_a_friendly_message(self):
        response = self.client.get(reverse("restaurants:list"), {"q": "sushi"})
        self.assertContains(response, "Nothing matches")

    # ---- restaurant page ----
    def test_menu_shows_available_dishes_only(self):
        response = self.client.get(reverse("restaurants:detail", args=[self.spice.pk]))
        self.assertContains(response, "Paneer Tikka")
        self.assertContains(response, "₹150")
        self.assertNotContains(response, "Secret Special")

    def test_menu_shows_quantity_and_cart_bar_for_items_in_the_cart(self):
        self.client.post(reverse("orders:add", args=[self.tikka.pk]))
        self.client.post(reverse("orders:add", args=[self.tikka.pk]))
        response = self.client.get(reverse("restaurants:detail", args=[self.spice.pk]))
        tikka = next(i for i in response.context["items"] if i.pk == self.tikka.pk)
        self.assertEqual(tikka.in_cart, 2)
        self.assertContains(response, "View cart")
        self.assertContains(response, "₹300")

    def test_cart_bar_is_hidden_on_other_restaurants(self):
        self.client.post(reverse("orders:add", args=[self.tikka.pk]))
        response = self.client.get(reverse("restaurants:detail", args=[self.pasta.pk]))
        self.assertNotContains(response, "View cart")

    # ---- dashboards ----
    def test_vendor_dashboard_stats_count_only_paid_orders(self):
        def order(status, total):
            o = Order.objects.create(customer=self.customer, restaurant=self.spice, status=status, total=Decimal(total))
            OrderLine.objects.create(order=o, item=self.tikka, name="Paneer Tikka", unit_price=Decimal("150"), quantity=1)

        order(Order.Status.PENDING_PAYMENT, "999")
        order(Order.Status.PAID, "300")
        order(Order.Status.PREPARING, "150")
        order(Order.Status.DELIVERED, "450")
        Order.objects.create(customer=self.customer, restaurant=self.pasta, status=Order.Status.PAID, total=Decimal("260"))

        self.client.force_login(self.vendor)
        response = self.client.get(reverse("restaurants:vendor_dashboard"))
        self.assertEqual(response.context["stats"], {"items": 3, "orders": 3, "to_prepare": 2, "revenue": Decimal("900")})
        self.assertContains(response, "₹900")

    def test_admin_dashboard_totals(self):
        Order.objects.create(customer=self.customer, restaurant=self.spice, status=Order.Status.PAID, total=Decimal("300"))
        Order.objects.create(customer=self.customer, restaurant=self.pasta, status=Order.Status.PENDING_PAYMENT, total=Decimal("260"))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.context["revenue"], Decimal("300"))
        self.assertEqual(response.context["order_count"], 1)
        self.assertEqual(response.context["restaurant_count"], 2)
        self.assertContains(response, "Platform overview")

    # ---- every page renders ----
    def test_public_pages_render(self):
        for name in ["restaurants:list", "orders:cart", "accounts:login", "accounts:signup"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_vendor_pages_render(self):
        self.client.force_login(self.vendor)
        pages = [
            reverse("restaurants:vendor_dashboard"),
            reverse("restaurants:item_create"),
            reverse("restaurants:item_edit", args=[self.tikka.pk]),
            reverse("restaurants:item_delete", args=[self.tikka.pk]),
        ]
        for url in pages:
            with self.subTest(page=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_new_vendor_sees_the_setup_page(self):
        newcomer = User.objects.create_user("vendor3", password="pass12345!", role=User.Role.VENDOR)
        self.client.force_login(newcomer)
        response = self.client.get(reverse("restaurants:vendor_dashboard"))
        self.assertContains(response, "Set up your restaurant")


class SeedDemoCommandTests(TestCase):
    def test_seed_creates_restaurants_and_is_safe_to_run_twice(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Restaurant.objects.count(), 15)
        paragon = User.objects.get(username="vendor_demo").restaurant
        self.assertEqual(paragon.name, "Paragon")
        self.assertEqual(paragon.city.key, "kozhikode")
        self.assertEqual(paragon.items.count(), 12)
        self.assertTrue(User.objects.get(username="admin_demo").is_superuser)
        # Every outlet sits inside the city it is listed in.
        for restaurant in Restaurant.objects.all():
            with self.subTest(restaurant=f"{restaurant.name}, {restaurant.area_name}"):
                self.assertEqual(location.nearest_city(restaurant.latitude, restaurant.longitude), restaurant.city)
        self.assertTrue(self.client.login(username="customer_demo", password="demo12345!"))


class StaticFilesTests(TestCase):
    def test_stylesheet_and_favicon_can_be_found(self):
        # Without STATICFILES_DIRS the pages would load with no styling at all.
        self.assertIsNotNone(finders.find("css/style.css"))
        self.assertIsNotNone(finders.find("img/favicon.svg"))

    def test_pages_link_the_stylesheet(self):
        response = self.client.get(reverse("restaurants:list"))
        self.assertContains(response, '/static/css/style.css')

    def test_stylesheet_and_scripts_carry_a_version_so_old_cached_copies_are_never_used(self):
        response = self.client.get(reverse("restaurants:list"))
        for path in ["css/style.css", "js/map.js", "js/location.js"]:
            with self.subTest(path=path):
                self.assertRegex(response.content.decode(), rf'/static/{path}\?v=\d+"')


class LocationMathTests(TestCase):
    def test_distance_between_known_places(self):
        _, koramangala = location.find_area("koramangala")
        _, indiranagar = location.find_area("indiranagar")
        distance = location.distance_km(koramangala.lat, koramangala.lng, indiranagar.lat, indiranagar.lng)
        self.assertAlmostEqual(distance, 4.0, delta=0.5)
        self.assertEqual(location.distance_km(12.9, 77.6, 12.9, 77.6), 0)

    def test_nearest_city_and_the_service_area(self):
        self.assertEqual(location.nearest_city(12.93, 77.62).key, "bengaluru")
        self.assertEqual(location.nearest_city(11.87, 75.37).key, "kannur")
        self.assertIsNone(location.nearest_city(28.61, 77.21))  # New Delhi: not served

    def test_delivery_window_adds_travel_time_to_kitchen_time(self):
        self.assertEqual(location.delivery_minutes(0, 20), (20, 25))
        self.assertEqual(location.delivery_minutes(4, 20), (30, 35))
        self.assertEqual(location.delivery_minutes(0, 0), (10, 15))  # never promises less than 10 minutes

    def test_parse_coordinates_rejects_bad_input(self):
        self.assertEqual(location.parse_coordinates("12.9", "77.6"), (12.9, 77.6))
        for lat, lng in [("abc", "77"), (None, None), ("91", "77"), ("12", "181")]:
            self.assertIsNone(location.parse_coordinates(lat, lng))

    def test_restaurant_without_coordinates_uses_its_area_centre(self):
        owner = User.objects.create_user("v", password="pass12345!", role=User.Role.VENDOR)
        restaurant = Restaurant.objects.create(owner=owner, name="New Place", area="thavakkara")
        _, area = location.find_area("thavakkara")
        self.assertEqual((restaurant.latitude, restaurant.longitude), (area.lat, area.lng))
        self.assertEqual(restaurant.city.name, "Kannur")


class LocationPagesTests(TestCase):
    def setUp(self):
        def outlet(username, name, area, radius=6):
            owner = User.objects.create_user(username, password="pass12345!", role=User.Role.VENDOR)
            restaurant = Restaurant.objects.create(owner=owner, name=name, area=area, delivery_radius_km=radius)
            MenuItem.objects.create(restaurant=restaurant, name=f"{name} Special", price=Decimal("200"), category="Mains")
            return restaurant

        self.kfc = outlet("v1", "KFC", "koramangala")
        self.dominos = outlet("v2", "Domino's", "hsr-layout")
        self.pizza_hut = outlet("v3", "Pizza Hut", "indiranagar", radius=3)
        self.paragon = outlet("v4", "Paragon", "nadakkavu")

    def _deliver_to(self, area):
        return self.client.post(reverse("restaurants:set_location"), {"area": area}, follow=True)

    def test_picking_an_area_saves_the_location_in_the_session(self):
        response = self._deliver_to("koramangala")
        self.assertEqual(self.client.session["location"]["label"], "Koramangala, Bengaluru")
        self.assertEqual(self.client.session["location"]["city"], "bengaluru")
        self.assertContains(response, "Delivering to Koramangala, Bengaluru.")

    def test_browser_coordinates_are_labelled_with_the_nearest_area(self):
        self.client.post(reverse("restaurants:set_location"), {"lat": "12.9360", "lng": "77.6250"})
        self.assertEqual(self.client.session["location"]["label"], "Near Koramangala, Bengaluru")

    def test_coordinates_outside_the_service_area_explain_where_cravio_delivers(self):
        response = self.client.post(reverse("restaurants:set_location"), {"lat": "28.61", "lng": "77.21"}, follow=True)
        self.assertIsNone(self.client.session["location"]["city"])
        self.assertContains(response, "does not deliver to your area yet")

    def test_bad_coordinates_are_rejected(self):
        response = self.client.post(reverse("restaurants:set_location"), {"lat": "x", "lng": ""}, follow=True)
        self.assertNotIn("location", self.client.session)
        self.assertContains(response, "We could not read that location.")

    def test_location_can_be_cleared(self):
        self._deliver_to("koramangala")
        self.client.post(reverse("restaurants:clear_location"))
        self.assertNotIn("location", self.client.session)

    def test_list_shows_the_location_city_nearest_first_and_out_of_range_last(self):
        self._deliver_to("koramangala")
        response = self.client.get(reverse("restaurants:list"))
        # Paragon is in Kozhikode, so it is not listed. Pizza Hut is about 4 km away but only
        # delivers within 3 km, so it goes after the places that can deliver.
        self.assertEqual([r.name for r in response.context["restaurants"]], ["KFC", "Domino's", "Pizza Hut"])
        self.assertEqual(response.context["nearby_count"], 2)
        self.assertContains(response, "Out of delivery range")
        self.assertContains(response, "min</span>")

    def test_city_tabs_filter_without_a_location(self):
        response = self.client.get(reverse("restaurants:list"), {"city": "kozhikode"})
        self.assertEqual([r.name for r in response.context["restaurants"]], ["Paragon"])
        response = self.client.get(reverse("restaurants:list"), {"city": "all"})
        self.assertEqual(len(response.context["restaurants"]), 4)

    def test_map_data_lists_every_restaurant_with_a_position(self):
        response = self.client.get(reverse("restaurants:list"))
        self.assertContains(response, 'id="map-data"')
        self.assertEqual(len(response.context["map_data"]["restaurants"]), 4)

    def test_menu_page_blocks_ordering_when_out_of_range(self):
        self._deliver_to("koramangala")
        response = self.client.get(reverse("restaurants:detail", args=[self.paragon.pk]))
        self.assertContains(response, "Out of delivery range.")
        self.assertNotContains(response, "to cart")

    def test_menu_page_shows_distance_time_and_sections(self):
        self._deliver_to("koramangala")
        response = self.client.get(reverse("restaurants:detail", args=[self.kfc.pk]))
        self.assertContains(response, "away")
        self.assertContains(response, "Add KFC Special to cart")
        self.assertEqual([name for name, _ in response.context["sections"]], ["Mains"])
        self.assertContains(response, "Non-vegetarian")
