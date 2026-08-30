"""
Optional recipe categorisation.

Sets each imported recipe's Mealie categories to its region of origin and what
kind of dish it is — "Indian + Curry + Main", "Italian + Pasta + Main",
"Breakfast". Off by default; set SET_CATEGORIES=true in .env to enable.

Region comes from the recipe's own Schema.org recipeCuisine where the site
publishes one, normalised through an alias table so "Tex-Mex" lands on Mexican
and "Sichuan" on Chinese, and non-regional values like "Vegan" or "Gluten Free"
are ignored. Where it is missing — which is most of the time — it is inferred
by scoring marker ingredients and title words. Distinctive markers (garam
masala, gochujang, berbere, doubanjiang) carry the decision; generic ones
(cilantro, lime, maple syrup) only break ties, so a kale salad does not become
Mexican for having coriander in it. No signal means no category, never a guess.

Dish type comes from the site's recipeCategory and keywords where present,
otherwise the title and URL slug. A recipe can hold several, capped at three.

Mealie only — Tandoor's organiser model is different and this does not touch it.

    SET_CATEGORIES=true
    CUISINE_MIN_SCORE=2     # raise to be stricter about regions
"""

import json
import logging
import os
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("dredger.categorise")

SET_CATEGORIES = os.getenv('SET_CATEGORIES', 'false').lower() == 'true'
try:
    CUISINE_MIN_SCORE = float(os.getenv('CUISINE_MIN_SCORE', 2))
except (TypeError, ValueError):
    CUISINE_MIN_SCORE = 2.0

MAX_DISH_TYPES = 3


# ---------------------------------------------------------------------------
# REGION OF ORIGIN
# ---------------------------------------------------------------------------

# Canonical names, and how the messy strings sites publish map onto them.
CUISINE_ALIASES = {
    'indian': 'Indian', 'north indian': 'Indian', 'south indian': 'Indian',
    'punjabi': 'Indian', 'gujarati': 'Indian', 'bengali': 'Indian',
    'sri lankan': 'Sri Lankan', 'nepali': 'Nepali', 'pakistani': 'Pakistani',
    'chinese': 'Chinese', 'sichuan': 'Chinese', 'szechuan': 'Chinese',
    'cantonese': 'Chinese', 'taiwanese': 'Taiwanese',
    'japanese': 'Japanese', 'korean': 'Korean',
    'thai': 'Thai', 'vietnamese': 'Vietnamese', 'filipino': 'Filipino',
    'indonesian': 'Indonesian', 'malaysian': 'Malaysian', 'burmese': 'Burmese',
    'asian': 'Asian', 'east asian': 'Asian', 'southeast asian': 'Asian',
    'mexican': 'Mexican', 'tex mex': 'Mexican', 'tex-mex': 'Mexican',
    'latin': 'Latin American', 'latin american': 'Latin American',
    'peruvian': 'Latin American', 'brazilian': 'Brazilian',
    'caribbean': 'Caribbean', 'jamaican': 'Caribbean', 'cuban': 'Caribbean',
    'italian': 'Italian', 'sicilian': 'Italian', 'tuscan': 'Italian',
    'french': 'French', 'spanish': 'Spanish', 'portuguese': 'Portuguese',
    'greek': 'Greek', 'mediterranean': 'Mediterranean',
    'british': 'British', 'english': 'British', 'scottish': 'British',
    'irish': 'Irish', 'welsh': 'British', 'uk': 'British',
    'american': 'American', 'southern': 'American', 'cajun': 'American',
    'creole': 'American', 'californian': 'American', 'canadian': 'Canadian',
    'german': 'German', 'austrian': 'German', 'swiss': 'German',
    'polish': 'Eastern European', 'russian': 'Eastern European',
    'ukrainian': 'Eastern European', 'hungarian': 'Eastern European',
    'eastern european': 'Eastern European',
    'nordic': 'Nordic', 'scandinavian': 'Nordic', 'swedish': 'Nordic',
    'danish': 'Nordic', 'norwegian': 'Nordic', 'finnish': 'Nordic',
    'turkish': 'Turkish', 'lebanese': 'Middle Eastern',
    'israeli': 'Middle Eastern', 'persian': 'Middle Eastern',
    'iranian': 'Middle Eastern', 'syrian': 'Middle Eastern',
    'middle eastern': 'Middle Eastern', 'moroccan': 'North African',
    'tunisian': 'North African', 'algerian': 'North African',
    'egyptian': 'North African', 'north african': 'North African',
    'ethiopian': 'Ethiopian', 'eritrean': 'Ethiopian',
    'nigerian': 'West African', 'ghanaian': 'West African',
    'senegalese': 'West African', 'west african': 'West African',
    'south african': 'African', 'kenyan': 'African', 'african': 'African',
    'hawaiian': 'Hawaiian', 'australian': 'Australian',
}

# Marker ingredients and title words. Weight 2 = distinctive enough on its own
# when paired with anything else; weight 1 = suggestive only.
CUISINE_MARKERS = {
    'Indian': [(2, r'\b(garam masala|asafoetida|hing|amchur|curry leaf|curry leaves|'
                   r'ghee substitute|besan|paneer|chana masala|tikka|masala dosa|'
                   r'idli|sambar|rajma|dal makhani|tandoori|biryani|naan|chapati|'
                   r'roti|paratha|jeera|methi|kadhi|poha|upma)\b'),
               (1, r'\b(turmeric|cumin seed|coriander seed|cardamom|mustard seed|'
                   r'basmati|lentil dal|dal|curry|chutney|ginger garlic paste)\b')],
    'Chinese': [(2, r'\b(shaoxing|doubanjiang|sichuan peppercorn|szechuan|'
                    r'chinkiang|black vinegar|hoisin|five spice|wood ear|'
                    r'bok choy|gai lan|mapo|kung pao|lo mein|chow mein|'
                    r'wonton|dumpling wrapper|char siu|dan dan)\b'),
                (1, r'\b(soy sauce|sesame oil|rice wine|scallion|ginger|'
                    r'stir fry|stir-fry|noodle)\b')],
    'Japanese': [(2, r'\b(miso|mirin|sake|dashi kombu|kombu|nori|wasabi|'
                     r'panko|udon|soba|ramen|teriyaki|edamame|shiso|'
                     r'yuzu|katsu|onigiri|tempura|okonomiyaki|matcha)\b'),
                 (1, r'\b(rice vinegar|sushi|japanese)\b')],
    'Korean': [(2, r'\b(gochujang|gochugaru|kimchi|doenjang|bibimbap|'
                   r'tteokbokki|banchan|bulgogi|japchae|perilla)\b'), (1, r'\b(korean)\b')],
    'Thai': [(2, r'\b(thai basil|red curry paste|green curry paste|massaman|'
                 r'pad thai|tom yum|tom kha|thai)\b'),
             (1, r'\b(lemongrass|galangal|kaffir lime|palm sugar|coconut milk|'
                 r'peanut|lime juice)\b')],
    'Indonesian': [(2, r'\b(rendang|kecap manis|gado gado|nasi goreng|sambal oelek|'
                       r'tempeh orek|indonesian|bumbu)\b'),
                   (1, r'\b(lemongrass|galangal|coconut milk|palm sugar|tamarind)\b')],
    'Malaysian': [(2, r'\b(laksa|nasi lemak|pandan|rendang|malaysian|'
                      r'char kway|roti canai)\b'),
                  (1, r'\b(lemongrass|coconut milk|tamarind)\b')],
    'Vietnamese': [(2, r'\b(pho|banh mi|rice paper|vermicelli noodle|'
                       r'nuoc cham|vietnamese)\b'), (1, r'\b(lemongrass|mint|coriander)\b')],
    'Mexican': [(2, r'\b(tortilla|masa harina|chipotle|adobo|poblano|jalape|'
                    r'ancho|guajillo|tomatillo|salsa verde|enchilada|'
                    r'taco|burrito|quesadilla|tostada|elote|pico de gallo|'
                    r'refried|mole|nopales)\b'),
                (1, r'\b(black bean|lime|cilantro|avocado|cumin)\b')],
    'Caribbean': [(2, r'\b(jerk seasoning|scotch bonnet|allspice|callaloo|'
                      r'plantain|ackee|jamaican|caribbean)\b'), (1, r'\b(coconut|thyme)\b')],
    'Italian': [(2, r'\b(arborio|risotto|passata|pasta e|gnocchi|polenta|'
                    r'lasagne|lasagna|bolognese|puttanesca|cacio|pesto|'
                    r'bruschetta|focaccia|ciabatta|tiramisu|orecchiette|'
                    r'pappardelle|tagliatelle|rigatoni|penne|spaghetti|'
                    r'balsamic|marinara)\b'),
                (1, r'\b(basil|oregano|olive oil|tomato|garlic)\b')],
    'French': [(2, r'\b(ratatouille|baguette|dijon|herbes de provence|'
                   r'tarte tatin|cassoulet|gratin|beurre|croissants?|'
                   r'bouillabaisse|provencal|proven|crepe|cr[eê]pe|'
                   r'shallot|tarragon|puy lentil)\b'), (1, r'\b(thyme|bay leaf|white wine)\b')],
    'Spanish': [(2, r'\b(paella|smoked paprika|piment[oó]n|sofrito|'
                    r'romesco|gazpacho|patatas bravas|manchego|saffron rice|'
                    r'spanish)\b'), (1, r'\b(saffron|olive|sherry vinegar)\b')],
    'Greek': [(2, r'\b(greek|tzatziki|spanakopita|dolma|orzo|'
                  r'kalamata|gyro|souvlaki|filo|phyllo)\b'), (1, r'\b(oregano|lemon|olive)\b')],
    'Middle Eastern': [(2, r'\b(za\'?atar|sumac|tahini sauce|labneh|baharat|'
                           r'pomegranate molasses|freekeh|bulgur|falafel|'
                           r'shawarma|baba ganoush|muhammara|fattoush|'
                           r'tabbouleh|halloumi|pita|hummus|dukkah|'
                           r'rose water|pistachio|persian|lebanese)\b'),
                       (1, r'\b(chickpea|parsley|mint|cinnamon)\b')],
    'Turkish': [(2, r'\b(turkish|pide|menemen|borek|b[oö]rek|'
                    r'pul biber|aleppo pepper)\b'), (1, r'\b(yogurt|bulgur)\b')],
    'North African': [(2, r'\b(harissa|ras el hanout|preserved lemon|couscous|'
                          r'tagine|moroccan|merguez|chermoula|'
                          r'north african)\b'), (1, r'\b(cinnamon|apricot|almond|date)\b')],
    'Ethiopian': [(2, r'\b(berbere|injera|teff|niter kibbeh|mitmita|'
                      r'ethiopian|shiro|wat\b)\b'), (1, r'\b(lentil|collard)\b')],
    'West African': [(2, r'\b(jollof|egusi|fufu|suya|scotch bonnet|'
                         r'nigerian|ghanaian|west african|plantain)\b'),
                     (1, r'\b(peanut|palm oil|okra)\b')],
    'British': [(2, r'\b(british|shepherd\'?s pie|cottage pie|toad in the hole|'
                    r'bubble and squeak|crumpet|scone|yorkshire pudding|'
                    r'bangers|mushy pea|marmite|piccalilli|treacle|'
                    r'sticky toffee|eccles|cornish|ploughman|'
                    r'full english|shortbread|flapjack|trifle)\b'),
                (1, r'\b(golden syrup|self raising|swede|parsnip|custard)\b')],
    'Irish': [(2, r'\b(irish|colcannon|champ|soda bread|boxty)\b'), (1, r'\b(potato|cabbage)\b')],
    'American': [(2, r'\b(cornbread|grits|biscuits and gravy|sloppy joe|'
                     r'mac and cheese|jambalaya|gumbo|po\'? ?boy|'
                     r'buffalo sauce|ranch dressing|s\'?mores|'
                     r'pumpkin pie|thanksgiving|bbq sauce|barbecue sauce|'
                     r'cajun|creole|pancake stack|brownie|'
                     r'chocolate chip cookie|meatloaf|coleslaw|'
                     r'sloppy|philly)\b'),
                 (1, r'\b(maple syrup|graham|all purpose flour|cup of)\b')],
    'German': [(2, r'\b(german|sauerkraut|spaetzle|sp[aä]tzle|pretzel|'
                   r'schnitzel|strudel|rye bread|quark)\b'), (1, r'\b(caraway|mustard|dill)\b')],
    'Eastern European': [(2, r'\b(borscht|borsch|pierogi|golabki|kasha|'
                             r'polish|ukrainian|russian|hungarian|'
                             r'paprikash|goulash|blini)\b'), (1, r'\b(beetroot|dill|cabbage)\b')],
    'Nordic': [(2, r'\b(nordic|scandinavian|swedish|danish|norwegian|'
                   r'cardamom bun|rye crisp|smorgas|lingonberry)\b'), (1, r'\b(rye|dill|caraway)\b')],
    'Mediterranean': [(2, r'\b(mediterranean)\b'), (1, r'\b(olive oil|lemon|oregano|chickpea)\b')],
}

CUISINE_RE = {name: [(w, re.compile(p, re.I)) for w, p in pats]
              for name, pats in CUISINE_MARKERS.items()}


def normalise_cuisine(raw) -> Optional[str]:
    """Map a site's recipeCuisine string onto a canonical name."""
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str):
        return None
    key = re.sub(r'[^a-z ]', ' ', raw.lower()).strip()
    key = re.sub(r'\s+', ' ', key)
    if key in CUISINE_ALIASES:
        return CUISINE_ALIASES[key]
    for alias, canonical in CUISINE_ALIASES.items():
        if re.search(rf'\b{re.escape(alias)}\b', key):
            return canonical
    return None


def infer_cuisine(title: str, ingredients: List[str]) -> Tuple[Optional[str], int]:
    """Score marker words across the title and ingredient list.

    Weak markers alone are not enough — cilantro and lime do not make a dish
    Mexican, and maple syrup does not make it American. A cuisine is only
    returned if at least one distinctive (weight 2) marker matched.
    """
    text = ' '.join([title or ''] + [str(i) for i in ingredients]).lower()
    scores, strong = {}, {}
    for name, pats in CUISINE_RE.items():
        score, strong_hits = 0, 0
        for weight, rx in pats:
            hits = len(rx.findall(text))
            if hits:
                score += weight * min(hits, 3)
                if weight >= 2:
                    strong_hits += hits
        if score:
            scores[name] = score
            strong[name] = strong_hits

    qualified = {n: sc for n, sc in scores.items() if strong.get(n)}
    if not qualified:
        return None, 0
    best = max(qualified, key=qualified.get)
    return best, qualified[best]


def cuisine_for(node: dict, ingredients: List[str]) -> Optional[str]:
    """Region of origin, or None when there is no real signal."""
    published = normalise_cuisine(node.get('recipeCuisine'))
    if published:
        return published

    title = node.get('name') or ''
    guess, score = infer_cuisine(title, ingredients)
    if guess and score >= CUISINE_MIN_SCORE:
        return guess
    return None


# ---------------------------------------------------------------------------
# DISH TYPE
# ---------------------------------------------------------------------------

# What sites publish in recipeCategory / keywords, mapped onto our names.
DISH_ALIASES = {
    'breakfast': 'Breakfast', 'brunch': 'Breakfast', 'morning': 'Breakfast',
    'main': 'Main', 'main course': 'Main', 'main dish': 'Main',
    'entree': 'Main', 'entrée': 'Main', 'dinner': 'Main', 'lunch': 'Main',
    'supper': 'Main', 'side': 'Side', 'side dish': 'Side',
    'appetizer': 'Starter', 'appetiser': 'Starter', 'starter': 'Starter',
    'salad': 'Salad', 'soup': 'Soup', 'stew': 'Stew', 'curry': 'Curry',
    'pasta': 'Pasta', 'noodles': 'Noodles', 'sandwich': 'Sandwich',
    'burger': 'Burger', 'pizza': 'Pizza', 'bowl': 'Bowl',
    'snack': 'Snack', 'snacks': 'Snack', 'dip': 'Dip', 'sauce': 'Sauce',
    'condiment': 'Sauce', 'condiments': 'Sauce', 'dressing': 'Dressing',
    'spread': 'Dip', 'bread': 'Bread', 'baking': 'Baking',
    'dessert': 'Dessert', 'desserts': 'Dessert', 'sweets': 'Dessert',
    'cake': 'Cake', 'cakes': 'Cake', 'cookies': 'Cookies',
    'cookie': 'Cookies', 'biscuits': 'Cookies', 'ice cream': 'Ice Cream',
    'frozen dessert': 'Ice Cream', 'drink': 'Drink', 'drinks': 'Drink',
    'beverage': 'Drink', 'beverages': 'Drink', 'smoothie': 'Smoothie',
    'smoothies': 'Smoothie', 'cocktail': 'Drink',
    'casserole': 'Bake', 'bake': 'Baking', 'baked goods': 'Baking',
    'stir fry': 'Stir-fry', 'stir-fry': 'Stir-fry', 'wrap': 'Sandwich',
    'meal prep': 'Meal Prep', 'batch cooking': 'Meal Prep',
}

# Title and URL markers, used when the published category is missing or vague.
DISH_MARKERS = {
    'Breakfast': r'\b(breakfast|granola|porridge|oatmeal|overnight oats|'
                 r'pancakes?|waffles?|french toast|muesli|scramble|'
                 r'shakshuka|hash browns?|bagels?|toast)\b',
    'Salad': r'\b(salad|slaw|coleslaw|tabbouleh|panzanella)\b',
    'Soup': r'\b(soup|broth|bisque|chowder|gazpacho|ramen|pho|minestrone)\b',
    'Stew': r'\b(stew|casserole|hotpot|hot pot|goulash|tagine|cassoulet|'
            r'gumbo|chill?i (con|sin|non) carne|(bean|lentil|veggie) chill?i)\b',
    'Curry': r'\b(curry|curried|masala|dal\b|daal|dhal|korma|tikka|rendang|'
             r'vindaloo|katsu curry)\b',
    'Pasta': r'\b(pasta|spaghetti|lasagne|lasagna|linguine|penne|rigatoni|'
             r'fettuccine|tagliatelle|macaroni|gnocchi|ravioli|orzo|'
             r'carbonara|bolognese)\b',
    'Noodles': r'\b(noodles?|udon|soba|lo mein|chow mein|pad thai|'
               r'rice noodles?|vermicelli)\b',
    'Stir-fry': r'\b(stir[ -]?fry|stir[ -]?fried|fried rice)\b',
    'Sandwich': r'\b(sandwich|wraps?|burritos?|tacos?|quesadillas?|panini|'
                r'bagel sandwich|banh mi|toastie)\b',
    'Burger': r'\b(burgers?|patties|patty)\b',
    'Pizza': r'\b(pizza|calzone|flatbread)\b',
    'Bowl': r'\b(bowls?|buddha bowl|grain bowl|poke)\b',
    'Rice': r'\b(risotto|paella|biryani|pilaf|pilau|jambalaya|'
            r'rice dish|congee|jollof)\b',
    'Dip': r'\b(dip|hummus|guacamole|baba ganoush|salsa|spread|pate|p[aâ]t[eé])\b',
    'Sauce': r'\b(sauce|pesto|marinara|gravy|chutney|relish|ketchup|'
             r'harissa|romesco|aioli|mayo|mayonnaise|seasoning|spice mix|'
             r'spice blend|marinade)\b',
    'Dressing': r'\b(dressing|vinaigrette)\b',
    'Bread': r'\b(bread|focaccia|ciabatta|baguette|naan|chapati|roti|'
             r'paratha|tortillas?|pitta|pita|scones?|crackers?|'
             r'breadsticks?|pretzels?|pupusas?|sourdough|'
             r'(bread|dinner|bread ?rolls?) rolls?|bread ?rolls?)\b',
    'Dessert': r'\b(dessert|pudding|trifle|tiramisu|mousse|cheesecake|'
               r'crumble|cobbler|tart|pie|doughnuts?|donuts?|fudge|'
               r'truffles?|ladoo|laddu|halwa|barfi|churros?)\b',
    'Cake': r'\b(cakes?|cupcakes?|muffins?|brownies?|blondies?|loaf cake|'
            r'banana bread|sponge)\b',
    'Cookies': r'\b(cookies?|biscuits?|shortbread|flapjacks?|'
               r'digestives?|macarons?)\b',
    'Ice Cream': r'\b(ice cream|nice cream|sorbet|gelato|popsicles?|'
                 r'ice lolly|frozen yogh?urt)\b',
    'Smoothie': r'\b(smoothies?|shakes?|juice|lassi)\b',
    'Drink': r'\b(drinks?|latte|coffee|tea\b|hot chocolate|cocktails?|'
             r'mocktails?|lemonade|horchata|chai)\b',
    'Snack': r'\b(snacks?|energy balls?|bliss balls?|bars?|popcorn|'
             r'trail mix|chips|crisps|nuggets?|fritters?|samosas?|'
             r'spring rolls?|dumplings?|gyoza|pakoras?)\b',
    'Side': r'\b(sides?|fries|mashed|roast potatoes|rice pilaf|pilau|'
            r'stuffing|pickles?|kimchi|sauerkraut)\b',
    'Staple': r'\b(vegan (cheese|butter|milk|cream|yogh?urt|mayo|egg)|'
              r'homemade (cheese|milk|butter|yogh?urt|pasta|stock)|'
              r'nut milk|oat milk|cashew cream|seitan|aquafaba|'
              r'spice (mix|blend)|seasoning)\b',
}

DISH_RE = {name: re.compile(p, re.I) for name, p in DISH_MARKERS.items()}

# Sweet things are never also a Main or a Side.
SWEET = {'Dessert', 'Cake', 'Cookies', 'Ice Cream', 'Smoothie', 'Drink'}
# Accompaniments are never a Main either.
NOT_MAIN = SWEET | {'Sauce', 'Dressing', 'Dip', 'Snack', 'Side', 'Bread',
                    'Baking', 'Starter', 'Staple'}
# Dishes that are a meal in themselves.
IMPLIES_MAIN = {'Curry', 'Stew', 'Soup', 'Pasta', 'Noodles', 'Stir-fry',
                'Pizza', 'Burger', 'Bowl', 'Bake', 'Sandwich', 'Rice'}

def _published_dish_types(node: dict) -> List[str]:
    found = []
    for key in ('recipeCategory', 'keywords'):
        raw = node.get(key)
        if isinstance(raw, str):
            raw = re.split(r'[,;/|]', raw)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, str):
                continue
            key_text = re.sub(r'[^a-z ]', ' ', item.lower()).strip()
            key_text = re.sub(r'\s+', ' ', key_text)
            hit = DISH_ALIASES.get(key_text)
            if hit and hit not in found:
                found.append(hit)
    return found


def dish_types(node: dict, url: str) -> List[str]:
    """Course and meal categories for a recipe. May be several."""
    title = node.get('name') or ''
    if isinstance(title, list):
        title = title[0] if title else ''
    slug = urlparse(url).path.replace('-', ' ')
    text = f"{title} {slug}"

    found = _published_dish_types(node)
    for name, rx in DISH_RE.items():
        if rx.search(text) and name not in found:
            found.append(name)

    if not found:
        return []

    # A dessert is not a main course; a dressing is not a side.
    if SWEET & set(found):
        found = [f for f in found if f not in ('Main', 'Side', 'Starter')]

    if 'Main' not in found and (IMPLIES_MAIN & set(found)) and not (NOT_MAIN & set(found)):
        found.append('Main')

    # Keep the most specific ones — Main and Side are the vaguest.
    order = {name: i for i, name in enumerate(found)}
    found.sort(key=lambda f: (f in ('Main', 'Side'), order[f]))
    return found[:MAX_DISH_TYPES]


# ---------------------------------------------------------------------------
# MEALIE WRITE-BACK
# ---------------------------------------------------------------------------

_category_cache = {}


def extract_recipe_jsonld(soup) -> Optional[dict]:
    """The Schema.org Recipe block from a page, if it has one."""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                types = node.get('@type')
                types = types if isinstance(types, list) else [types]
                if 'Recipe' in types:
                    return node
                for key in ('@graph', 'mainEntity', 'itemListElement'):
                    if key in node:
                        stack.append(node[key])
    return None


def categories_for(soup, url: str) -> List[str]:
    """Region and dish types for a recipe page. May be empty."""
    node = extract_recipe_jsonld(soup)
    if not node:
        return []

    raw = node.get('recipeIngredient') or node.get('ingredients') or []
    if isinstance(raw, str):
        raw = [raw]
    ingredients = [i for i in raw if isinstance(i, str)]

    cuisine = cuisine_for(node, ingredients)
    return ([cuisine] if cuisine else []) + dish_types(node, url)


def _ensure_category(session, mealie_url: str, headers: dict,
                     name: str) -> Optional[dict]:
    if not _category_cache:
        try:
            r = session.get(f"{mealie_url}/api/organizers/categories",
                            headers=headers, params={"perPage": 200}, timeout=20)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    _category_cache[item['name'].lower()] = item
        except Exception as e:
            logger.debug(f"Category list failed: {e}")

    if name.lower() in _category_cache:
        return _category_cache[name.lower()]

    try:
        r = session.post(f"{mealie_url}/api/organizers/categories",
                         headers=headers, json={"name": name}, timeout=20)
        if r.status_code in (200, 201):
            category = r.json()
            _category_cache[name.lower()] = category
            return category
        if r.status_code == 409:
            _category_cache.clear()
            return _ensure_category(session, mealie_url, headers, name)
    except Exception as e:
        logger.debug(f"Category create failed for {name}: {e}")
    return None


def apply_categories(session, mealie_url: str, token: str, slug: str,
                     categories: List[str]) -> bool:
    """Attach categories to a recipe Mealie has just imported."""
    if not (slug and categories):
        return False

    headers = {"Authorization": f"Bearer {token}"}
    objects = [c for c in (_ensure_category(session, mealie_url, headers, name)
                           for name in categories) if c]
    if not objects:
        return False

    try:
        r = session.patch(f"{mealie_url}/api/recipes/{slug}", headers=headers,
                          json={"recipeCategory": objects}, timeout=20)
        if r.status_code in (200, 201):
            logger.info(f"   🏷️  {slug}: {' + '.join(categories)}")
            return True
        logger.warning(f"   Categorising failed for {slug}: HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"   Categorising error for {slug}: {e}")
    return False
