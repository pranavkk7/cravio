from decimal import Decimal

from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand

from accounts.models import User
from restaurants.models import MenuItem, Restaurant

DEMO_PASSWORD = "demo12345!"  # demo data only; never reuse for real accounts

# Demo data for a portfolio project. Brand names and signature dishes are real, prices are approximate,
# and outlet positions are close to the real ones. Cravio is not affiliated with any of these brands.
# Each dish: (section, name, description, price, is_veg, photo). Photos live in static/img/food/.
BRANDS = {
    "paragon": {
        "name": "Paragon",
        "cuisine": "Malabar, Seafood, Biryani",
        "description": "Kozhikode's legendary Malabar kitchen, cooking since 1939.",
        "prep": 20,
        "cover": "biryani",
        "menu": [
            ("Biryani", "Malabar Chicken Biryani", "Jeerakasala rice layered with spiced chicken", "280", False, "biryani"),
            ("Biryani", "Mutton Biryani", "Slow-cooked mutton, ghee rice and fried onions", "390", False, "biryani-2"),
            ("Biryani", "Prawns Biryani", "Malabar prawns dum-cooked with jeerakasala rice", "380", False, "biryani-3"),
            ("Kerala mains", "Fish Mango Curry", "Fish simmered in coconut milk with raw mango", "260", False, "fish-curry"),
            ("Kerala mains", "Mutton Varattiyathu", "Mutton roasted dry with shallots and pepper", "360", False, "curry"),
            ("Kerala mains", "Chicken Stew", "Mild coconut milk stew, perfect with appam", "180", False, ""),
            ("Kerala mains", "Koonthal Ularthiyathu", "Squid stir-fried with coconut slivers", "320", False, "seafood"),
            ("Kerala mains", "Kozhi Porichathu", "Malabar-style fried chicken", "260", False, "fried-chicken"),
            ("Breads", "Appam (2 pcs)", "Lacy rice hoppers with soft centres", "40", True, "appam"),
            ("Breads", "Kerala Porotta", "Flaky layered flatbread", "20", True, "porotta"),
            ("Desserts and drinks", "Tender Coconut Pudding", "Chilled pudding with tender coconut", "140", True, "dessert"),
            ("Desserts and drinks", "Sulaimani", "Black tea with lemon and spices", "25", True, "tea"),
        ],
    },
    "rahmath": {
        "name": "Rahmath Hotel",
        "cuisine": "Malabar, Biryani",
        "description": "Mananchira institution, famous across Kozhikode for its beef biryani.",
        "prep": 15,
        "cover": "biryani-2",
        "menu": [
            ("Biryani", "Beef Biryani", "The house special: tender beef and fragrant rice", "220", False, "biryani-2"),
            ("Biryani", "Chicken Biryani", "Malabar-style with jeerakasala rice", "200", False, "biryani"),
            ("Biryani", "Mutton Biryani", "Rich, slow-cooked mutton biryani", "300", False, "biryani-3"),
            ("Sides", "Beef Fry", "Beef roasted with coconut bits and curry leaves", "160", False, "curry"),
            ("Sides", "Chicken Fry", "Crispy, spicy fried chicken", "170", False, "fried-chicken"),
            ("Sides", "Porotta", "Flaky layered flatbread", "15", True, "porotta"),
            ("Drinks", "Sulaimani", "Black tea with lemon and spices", "15", True, "tea"),
        ],
    },
    "nahdi": {
        "name": "Nahdi Mandi",
        "cuisine": "Arabian, Mandi",
        "description": "Smoky Arabian kuzhi mandi and al faham, made for sharing.",
        "prep": 25,
        "cover": "mandi",
        "menu": [
            ("Mandi", "Chicken Kuzhi Mandi (Quarter)", "Pit-cooked chicken on fragrant mandi rice", "300", False, "mandi"),
            ("Mandi", "Chicken Kuzhi Mandi (Half)", "Serves two, with salad and sauces", "560", False, ""),
            ("Mandi", "Al Faham Mandi (Quarter)", "Charcoal-grilled chicken on mandi rice", "330", False, "al-faham"),
            ("Mandi", "Al Faham Mandi (Half)", "Serves two, with salad and sauces", "600", False, ""),
            ("Mandi", "Fil Fil Al Faham Mandi", "Pepper-spiced al faham on mandi rice", "340", False, ""),
            ("Mandi", "Mutton Mandi (Quarter)", "Slow-cooked mutton on mandi rice", "460", False, ""),
            ("Sides", "Hummus with Kubboos", "Creamy chickpea dip and Arabic bread", "140", True, "hummus"),
            ("Sides", "Garlic Mayonnaise", "The classic mandi dip", "30", False, ""),
            ("Drinks", "Lime Mint Cooler", "Fresh lime blended with mint", "90", True, "lime-mint"),
        ],
    },
    "kfc": {
        "name": "KFC",
        "cuisine": "Fried chicken, Burgers",
        "description": "Hot and crispy fried chicken, burgers and buckets.",
        "prep": 15,
        "cover": "fried-chicken",
        "menu": [
            ("Chicken", "Hot & Crispy Chicken (2 pc)", "Spicy, crunchy bone-in chicken", "229", False, "fried-chicken"),
            ("Chicken", "Chicken Bucket (8 pc)", "Eight pieces to share", "659", False, ""),
            ("Chicken", "Chicken Popcorn (Medium)", "Bite-sized boneless chicken", "179", False, "chicken-65"),
            ("Chicken", "Chicken Strips (3 pc)", "Tender boneless strips", "169", False, ""),
            ("Burgers", "Classic Zinger Burger", "Crispy chicken fillet, lettuce and mayo", "199", False, "burger"),
            ("Burgers", "Veg Zinger Burger", "Crispy veg patty with lettuce and mayo", "159", True, ""),
            ("Sides and drinks", "French Fries (Medium)", "Salted and crisp", "119", True, "fries"),
            ("Sides and drinks", "Pepsi (475 ml)", "Chilled soft drink", "69", True, "cola"),
        ],
    },
    "dominos": {
        "name": "Domino's Pizza",
        "cuisine": "Pizza",
        "description": "Hand-tossed pizzas, garlic breadsticks and choco lava cake.",
        "prep": 15,
        "cover": "pizza",
        "menu": [
            ("Pizzas (medium)", "Margherita", "Classic cheese and tomato", "299", True, "pizza"),
            ("Pizzas (medium)", "Farmhouse", "Onion, capsicum, tomato and mushroom", "459", True, "pizza-2"),
            ("Pizzas (medium)", "Peppy Paneer", "Paneer, capsicum and red paprika", "459", True, ""),
            ("Pizzas (medium)", "Chicken Golden Delight", "Barbeque chicken, golden corn and extra cheese", "499", False, ""),
            ("Pizzas (medium)", "Chicken Dominator", "Loaded with five kinds of chicken", "599", False, ""),
            ("Sides", "Garlic Breadsticks", "Baked with garlic butter and herbs", "129", True, "garlic-bread"),
            ("Sides", "Stuffed Garlic Bread", "Filled with cheese and sweet corn", "169", True, ""),
            ("Desserts", "Choco Lava Cake", "Warm cake with a molten chocolate centre", "109", True, "lava-cake"),
        ],
    },
    "pizzahut": {
        "name": "Pizza Hut",
        "cuisine": "Pizza, Pasta",
        "description": "Thick pan pizzas loaded with toppings, plus pasta and sides.",
        "prep": 20,
        "cover": "pizza-2",
        "menu": [
            ("Pan pizzas (medium)", "Margherita", "Mozzarella and tangy tomato sauce", "349", True, "pizza-2"),
            ("Pan pizzas (medium)", "Veggie Supreme", "Onion, capsicum, mushroom, olives and corn", "489", True, "pizza"),
            ("Pan pizzas (medium)", "Tandoori Paneer", "Tandoori paneer, onion and capsicum", "499", True, ""),
            ("Pan pizzas (medium)", "Chicken Tikka", "Chicken tikka with onion and capsicum", "529", False, ""),
            ("Pan pizzas (medium)", "Chicken Supreme", "Three kinds of chicken with olives", "569", False, ""),
            ("Pasta and sides", "Creamy Tomato Pasta", "Penne in a creamy tomato sauce", "199", True, "pasta"),
            ("Pasta and sides", "Garlic Bread", "Toasted with garlic butter", "149", True, "garlic-bread"),
            ("Pasta and sides", "Pepsi (475 ml)", "Chilled soft drink", "69", True, "cola"),
        ],
    },
    "blaban": {
        "name": "B.Laban",
        "cuisine": "Egyptian desserts",
        "description": "Egyptian desserts: kunafa, Umm Ali, salankatia and ambalyh.",
        "prep": 10,
        "cover": "kunafa",
        "menu": [
            ("Signatures", "Salankatia Mango", "Layers of cream, cake and fresh mango", "280", True, "mango-dessert"),
            ("Signatures", "Salankatia Pistachio", "Cream and cake with pistachio sauce", "320", True, ""),
            ("Signatures", "Ambalyh Mango", "Rice pudding crowned with mango", "300", True, ""),
            ("Signatures", "Kunafa Pistachio", "Crisp kunafa with pistachio cream", "340", True, "kunafa"),
            ("Umm Ali and more", "Umm Ali (Plain)", "Warm Egyptian bread pudding with nuts", "220", True, "dessert"),
            ("Umm Ali and more", "Crispy Umm Ali Lotus", "Umm Ali with Lotus biscuit crumble", "290", True, ""),
            ("Umm Ali and more", "Koushiri Nutella", "Layered rice pudding with Nutella", "260", True, ""),
        ],
    },
    "odhens": {
        "name": "Odhen's Hotel",
        "cuisine": "Kannur seafood, Meals",
        "description": "Kannur's lunchtime legend for fish meals and seafood fries.",
        "prep": 15,
        "cover": "fish-meals",
        "menu": [
            ("Meals", "Fish Meals", "Kerala rice with fish curry, thoran and pickle", "130", False, "fish-meals"),
            ("Meals", "Veg Meals", "Kerala rice with sambar, thoran and pickle", "90", True, "meals"),
            ("Seafood fries", "Ayala Fry (Mackerel)", "Masala-coated and pan-fried", "90", False, "fish-fry"),
            ("Seafood fries", "Mathi Fry (Sardine)", "Crisp fried sardines", "60", False, ""),
            ("Seafood fries", "Kallummakkaya Fry (Mussels)", "A Malabar coast speciality", "160", False, ""),
            ("Seafood fries", "Koonthal Fry (Squid)", "Spicy fried squid rings", "200", False, "seafood"),
            ("Seafood fries", "Prawns Roast", "Prawns roasted with onion and spices", "240", False, "curry"),
        ],
    },
    "meghana": {
        "name": "Meghana Foods",
        "cuisine": "Andhra, Biryani",
        "description": "Bengaluru's much-loved Andhra-style biryani house.",
        "prep": 20,
        "cover": "biryani-3",
        "menu": [
            ("Biryani", "Chicken Boneless Biryani", "The bestseller: spicy boneless chicken biryani", "360", False, "biryani-3"),
            ("Biryani", "Meghana Special Chicken Biryani", "Loaded with extra chicken pieces", "390", False, "biryani"),
            ("Biryani", "Mutton Biryani", "Andhra-style mutton biryani", "420", False, "biryani-2"),
            ("Biryani", "Paneer Biryani", "Paneer cubes in spiced biryani rice", "320", True, ""),
            ("Biryani", "Veg Biryani", "Mixed vegetable biryani", "270", True, ""),
            ("Starters", "Chicken 65", "Deep-fried chicken with curry leaves", "300", False, "chicken-65"),
            ("Starters", "Andhra Chilli Chicken", "Fiery green chilli chicken", "320", False, "curry"),
        ],
    },
}

# (username, brand, area key, address, latitude, longitude, delivery radius in km).
# The first vendor keeps the simple name used in the README.
OUTLETS = [
    ("vendor_demo", "paragon", "nadakkavu", "Kannur Road, near CH Over Bridge, Kozhikode", 11.2620, 75.7812, 6),
    ("vendor_rahmath", "rahmath", "mananchira", "Aravind Ghosh Road, Mananchira, Kozhikode", 11.2546, 75.7808, 5),
    ("vendor_nahdi_kkd", "nahdi", "mananchira", "Red Cross Road, near Tagore Hall, Kozhikode", 11.2556, 75.7745, 6),
    ("vendor_kfc_kkd", "kfc", "thondayad", "HiLITE Mall food court, Thondayad, Kozhikode", 11.2482, 75.8339, 7),
    ("vendor_blaban_kkd", "blaban", "beach-road", "Beach Road, Kozhikode", 11.2575, 75.7708, 5),
    ("vendor_odhens", "odhens", "fort-road", "Onden Road, Kannur", 11.8728, 75.3697, 5),
    ("vendor_dominos_knr", "dominos", "thavakkara", "Thavakkara, Kannur", 11.8768, 75.3726, 6),
    ("vendor_blaban_knr", "blaban", "thana", "Thana, Kannur", 11.8848, 75.3795, 5),
    ("vendor_paragon_blr", "paragon", "mg-road", "1 Shobha, St. Marks Road, Bengaluru", 12.9701, 77.6011, 7),
    ("vendor_nahdi_blr", "nahdi", "btm-layout", "Opposite Madiwala Police Station, BTM Layout, Bengaluru", 12.9225, 77.6176, 7),
    ("vendor_kfc_blr", "kfc", "koramangala", "Koramangala 5th Block, Bengaluru", 12.9345, 77.6190, 6),
    ("vendor_dominos_blr", "dominos", "hsr-layout", "HSR Layout Sector 1, Bengaluru", 12.9121, 77.6446, 6),
    ("vendor_pizzahut", "pizzahut", "indiranagar", "100 Feet Road, Indiranagar, Bengaluru", 12.9719, 77.6408, 6),
    ("vendor_meghana", "meghana", "koramangala", "Jyoti Nivas College Road, Koramangala, Bengaluru", 12.9331, 77.6155, 7),
    ("vendor_blaban_blr", "blaban", "koramangala", "Koramangala 6th Block, Bengaluru", 12.9389, 77.6201, 5),
]


def photo(key):
    """The static path of a food photo, or "" when that photo is not in the project.

    Each photo is used at most once per restaurant, so no menu shows the same picture twice; dishes
    without a fitting photo get "" and the menu shows a tile instead."""
    path = f"img/food/{key}.jpg"
    return path if key and finders.find(path) else ""


class Command(BaseCommand):
    help = "Create demo users and 15 restaurant outlets in Kozhikode, Kannur and Bengaluru. Safe to run again."

    def _user(self, username, **defaults):
        user, _ = User.objects.get_or_create(username=username, defaults=defaults)
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def handle(self, *args, **options):
        self._user("admin_demo", is_staff=True, is_superuser=True)
        self._user("customer_demo", role=User.Role.CUSTOMER)

        for username, brand_key, area, address, lat, lng, radius in OUTLETS:
            brand = BRANDS[brand_key]
            owner = self._user(username, role=User.Role.VENDOR)
            restaurant, _ = Restaurant.objects.update_or_create(owner=owner, defaults={
                "name": brand["name"], "cuisine": brand["cuisine"], "description": brand["description"],
                "area": area, "address": address, "latitude": lat, "longitude": lng,
                "delivery_radius_km": Decimal(radius), "prep_minutes": brand["prep"], "cover_image": photo(brand["cover"]),
            })
            for section, dish, text, price, is_veg, image in brand["menu"]:
                MenuItem.objects.update_or_create(restaurant=restaurant, name=dish, defaults={
                    "category": section, "description": text, "price": Decimal(price), "is_veg": is_veg, "image": photo(image),
                })

        if options["verbosity"] == 0:
            return
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(OUTLETS)} restaurants in Kozhikode, Kannur and Bengaluru. "
            "Log in as admin_demo, vendor_demo or customer_demo "
            "(password in accounts/management/commands/seed_demo.py)."
        ))
