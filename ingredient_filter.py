"""
Optional ingredient exclusion filter.

Rejects recipes whose ingredient list contains terms you don't want, before
they reach your library. Off by default — set EXCLUDE_PRESET and/or
EXCLUDE_INGREDIENTS in .env to enable.

    EXCLUDE_PRESET=vegan              # vegan, vegetarian, gluten, nuts, alcohol
    EXCLUDE_PRESET=vegetarian,nuts    # combine presets
    EXCLUDE_INGREDIENTS=cilantro,fennel   # plus your own terms

Matching is word-boundary aware and case-insensitive, and each preset carries
an allow list of phrases that would otherwise be false positives — "peanut
butter" is not butter, "eggplant" is not egg, "gluten free flour" is not
gluten. Allowed phrases are removed from the line before the exclusions are
applied.

Custom terms from EXCLUDE_INGREDIENTS get no such guard, so prefer specific
words. Add your own exceptions with EXCLUDE_ALLOW if you need them.
"""

import re
from typing import List, Optional, Tuple

# --- PRESETS -----------------------------------------------------------------
# Each preset is (allow patterns, exclude patterns). Allow is applied first.

PRESETS = {
    "vegan": (
        [
            r'\b(vegan|plant[- ]based|dairy[- ]free|egg[- ]free|non[- ]dairy|'
            r'meat[- ]free|vegetarian|mock|faux|imitation)\s+[\w\- ]{0,20}',
            r'\b(peanut|almond|cashew|nut|seed|sunflower|apple|cocoa|coconut|'
            r'shea|tahini)\s+butter\b',
            r'\bbutter(nut|head|milk powder|fly|cup squash)\b',
            r'\bbutter\s+(bean|lettuce)s?\b',
            r'\b(coconut|almond|soy|soya|oat|rice|cashew|hemp|flax|pea|'
            r'macadamia|walnut|hazelnut|quinoa|nut)\s+'
            r'(milk|cream|yogh?urt|creamer)\b',
            r'\bmilk\s+thistle\b',
            r'\bcream\s+of\s+(tartar|wheat)\b',
            r'\bcreamed\s+(corn|spinach)\b',
            r'\begg\s*plant\b|\baubergine\b',
            r'\b(flax|chia|aquafaba|tofu)\s+egg\b|\begg\s+replacer\b',
            r'\bchick\s*pea\w*\b|\bgarbanzo\b',
            r'\bbeef\s*(steak)?\s+tomato\w*\b',
            r'\b(oyster|king oyster|lion\'?s mane|chicken of the woods|'
            r'hen of the woods|maitake)\s*(mushroom)?s?\b',
            r'\bcrab\s+apple\w*\b',
            r'\bhoney\s*(dew|crisp|nut squash)\b',
            r'\bnutritional\s+yeast\b',
            r'\bcheese\s*cloth\b',
            r'\bfish\s*less\b|\bchick\s*less\b|\bbeef\s*less\b',
            r'\bhamburger\s+(bun|roll)s?\b|\bburger\s+bun\w*\b',
            r'\bcoconut\s+(oil|sugar|flour|water|aminos|flakes?|shreds?|bacon)\b',
            r'\bsoy\s+curls?\b',
        ],
        [
            # dairy & eggs
            r'\bmilk\b', r'\bbuttermilk\b', r'\bbutter\b', r'\bghee\b',
            r'\bcreams?\b', r'\bcr[eè]me\s+fra[iî]che\b', r'\bhalf[- ]and[- ]half\b',
            r'\bsour cream\b', r'\bcondensed milk\b', r'\bevaporated milk\b',
            r'\bcheeses?\b', r'\bparmesan\b', r'\bparmigiano\b', r'\bpecorino\b',
            r'\bmozzarella\b', r'\bcheddar\b', r'\bfeta\b', r'\bricotta\b',
            r'\bmascarpone\b', r'\bhalloumi\b', r'\bpaneer\b', r'\bgruy[eè]re\b',
            r'\bbrie\b', r'\bgorgonzola\b', r'\bcotija\b', r'\bqueso\b',
            r'\byogh?urt\b', r'\bskyr\b', r'\bquark\b', r'\bcustard\b',
            r'\bcurds?\b', r'\bwhey\b', r'\bcasein\b',
            r'\beggs?\b', r'\bmayonnaise\b', r'\bmayo\b', r'\bmeringue\b',
            # meat & poultry
            r'\bchicken\b', r'\bbeef\b', r'\bsteak\b', r'\bpork\b', r'\bbacon\b',
            r'\bham\b', r'\bsausages?\b', r'\blamb\b', r'\bmutton\b', r'\bveal\b',
            r'\bturkey\b', r'\bduck\b', r'\bvenison\b', r'\bmince\b',
            r'\bbrisket\b', r'\bpepperoni\b', r'\bsalami\b', r'\bprosciutto\b',
            r'\bchorizo\b', r'\bpancetta\b', r'\bmeatballs?\b', r'\bribs?\b',
            r'\bthighs?\b', r'\bdrumsticks?\b', r'\bpoultry\b', r'\bmeat\b',
            # fish & shellfish
            r'\bfish\b', r'\bsalmon\b', r'\btuna\b', r'\banchov\w+\b', r'\bcod\b',
            r'\bhaddock\b', r'\bsardines?\b', r'\bmackerel\b', r'\btrout\b',
            r'\bprawns?\b', r'\bshrimps?\b', r'\bcrab\b', r'\blobster\b',
            r'\boysters?\b', r'\bmussels?\b', r'\bclams?\b', r'\bsquid\b',
            r'\bcalamari\b', r'\boctopus\b', r'\bscallops?\b', r'\bcaviar\b',
            r'\broe\b', r'\bbonito\b', r'\bkatsuobushi\b', r'\bdashi\b',
            r'\bshellfish\b',
            # fats, stocks, additives
            r'\blard\b', r'\btallow\b', r'\bsuet\b', r'\bschmaltz\b',
            r'\bbone broth\b', r'\bchicken (stock|broth|bouillon)\b',
            r'\bbeef (stock|broth|bouillon)\b', r'\bgelatin\w*\b',
            r'\bcollagen\b', r'\balbumin\b', r'\bisinglass\b', r'\bcarmine\b',
            r'\bcochineal\b', r'\bshellac\b', r'\brennet\b', r'\bhoney\b',
            r'\broyal jelly\b', r'\bworcestershire\b',
        ],
    ),
    "vegetarian": (
        [
            r'\b(vegan|vegetarian|plant[- ]based|meat[- ]free|mock|faux|'
            r'imitation)\s+[\w\- ]{0,20}',
            r'\bbeef\s*(steak)?\s+tomato\w*\b',
            r'\b(oyster|king oyster|chicken of the woods|hen of the woods)'
            r'\s*(mushroom)?s?\b',
            r'\bcrab\s+apple\w*\b',
            r'\bhamburger\s+(bun|roll)s?\b|\bburger\s+bun\w*\b',
            r'\bfish\s*less\b|\bchick\s*less\b|\bbeef\s*less\b',
        ],
        [
            r'\bchicken\b', r'\bbeef\b', r'\bsteak\b', r'\bpork\b', r'\bbacon\b',
            r'\bham\b', r'\bsausages?\b', r'\blamb\b', r'\bmutton\b', r'\bveal\b',
            r'\bturkey\b', r'\bduck\b', r'\bvenison\b', r'\bbrisket\b',
            r'\bpepperoni\b', r'\bsalami\b', r'\bprosciutto\b', r'\bchorizo\b',
            r'\bpancetta\b', r'\bpoultry\b', r'\bmeat\b',
            r'\bfish\b', r'\bsalmon\b', r'\btuna\b', r'\banchov\w+\b', r'\bcod\b',
            r'\bprawns?\b', r'\bshrimps?\b', r'\bcrab\b', r'\blobster\b',
            r'\boysters?\b', r'\bmussels?\b', r'\bclams?\b', r'\bsquid\b',
            r'\bscallops?\b', r'\bshellfish\b', r'\bfish sauce\b',
            r'\boyster sauce\b', r'\bdashi\b', r'\bbonito\b',
            r'\blard\b', r'\btallow\b', r'\bsuet\b', r'\bgelatin\w*\b',
            r'\bbone broth\b', r'\bchicken (stock|broth|bouillon)\b',
            r'\bbeef (stock|broth|bouillon)\b', r'\bworcestershire\b',
            r'\brennet\b',
        ],
    ),
    "gluten": (
        [
            r'\b(gluten[- ]free|gf)\s+[\w\- ]{0,20}',
            r'\b(almond|coconut|rice|chickpea|gram|buckwheat|corn|oat)\s+flour\b',
            r'\bbuckwheat\b', r'\brice noodles?\b', r'\bcorn tortillas?\b',
            r'\bcertified gluten free oats\b',
        ],
        [
            r'\bwheat\b', r'\bflour\b', r'\bbread\w*\b', r'\bpasta\b',
            r'\bspaghetti\b', r'\bnoodles?\b', r'\bcouscous\b', r'\bbulgur\b',
            r'\bsemolina\b', r'\bspelt\b', r'\bfarro\b', r'\bbarley\b',
            r'\brye\b', r'\bseitan\b', r'\bvital wheat gluten\b',
            r'\bpanko\b', r'\bcracker\w*\b', r'\bpastry\b', r'\bfilo\b',
            r'\bphyllo\b', r'\bpuff pastry\b', r'\bsoy sauce\b',
            r'\bmalt\b', r'\bbeer\b',
        ],
    ),
    "nuts": (
        [
            r'\bnutmeg\b', r'\bnutritional yeast\b', r'\bbutternut\b',
            r'\bnut[- ]free\b', r'\bwater chestnuts?\b',
        ],
        [
            r'\balmonds?\b', r'\bcashews?\b', r'\bwalnuts?\b', r'\bpecans?\b',
            r'\bpistachios?\b', r'\bhazelnuts?\b', r'\bmacadamias?\b',
            r'\bbrazil nuts?\b', r'\bpine nuts?\b', r'\bpeanuts?\b',
            r'\bpeanut butter\b', r'\bnut butter\b', r'\bmarzipan\b',
            r'\bpraline\b', r'\bnuts?\b', r'\bnut milk\b', r'\bfrangipane\b',
        ],
    ),
    "alcohol": (
        [
            r'\b(non[- ]?alcoholic|alcohol[- ]free|0%)\s+[\w\- ]{0,20}',
            r'\b(white|red|rice|sherry|balsamic|apple cider)\s+wine\s+vinegar\b',
            r'\bvanilla extract\b',
        ],
        [
            r'\bwines?\b', r'\bbeers?\b', r'\blagers?\b', r'\bales?\b',
            r'\bstout\b', r'\bcider\b', r'\brum\b', r'\bbrandy\b', r'\bvodka\b',
            r'\bwhisk(e)?y\b', r'\bbourbon\b', r'\bgin\b', r'\btequila\b',
            r'\bliqueur\b', r'\bkirsch\b', r'\bmarsala\b', r'\bsherry\b',
            r'\bport\b', r'\bvermouth\b', r'\bsake\b', r'\bshaoxing\b',
            r'\bmirin\b', r'\bamaretto\b', r'\bkahlua\b', r'\bchampagne\b',
            r'\bprosecco\b',
        ],
    ),
}


def _compile(patterns: List[str]):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


class IngredientFilter:
    """Decides whether a recipe's ingredients are acceptable."""

    def __init__(self, presets: List[str], extra_terms: List[str],
                 extra_allow: List[str]):
        allow, exclude = [], []

        for name in presets:
            name = name.strip().lower()
            if not name:
                continue
            if name not in PRESETS:
                raise ValueError(
                    f"Unknown EXCLUDE_PRESET '{name}'. "
                    f"Available: {', '.join(sorted(PRESETS))}"
                )
            preset_allow, preset_exclude = PRESETS[name]
            allow += preset_allow
            exclude += preset_exclude

        for term in extra_terms:
            term = term.strip()
            if term:
                exclude.append(rf'\b{re.escape(term)}\b')

        for term in extra_allow:
            term = term.strip()
            if term:
                allow.append(rf'\b{re.escape(term)}\b')

        self.allow = _compile(allow)
        self.exclude = [(re.compile(p, re.IGNORECASE), p) for p in exclude]
        self.enabled = bool(self.exclude)

    def check(self, ingredients: List[str]) -> Tuple[bool, Optional[str]]:
        """Return (acceptable, reason_if_not)."""
        if not self.enabled:
            return True, None

        for raw in ingredients:
            line = re.sub(r'\s+', ' ', str(raw)).lower()
            for allowed in self.allow:
                line = allowed.sub(' ', line)
            for rx, pattern in self.exclude:
                if rx.search(line):
                    return False, f"excluded ingredient in '{str(raw).strip()[:50]}'"
        return True, None


def extract_ingredients(soup) -> List[str]:
    """Ingredient lines from a page's Schema.org JSON-LD recipe block."""
    import json

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
                    raw = (node.get('recipeIngredient')
                           or node.get('ingredients') or [])
                    if isinstance(raw, str):
                        raw = [raw]
                    return [i for i in raw if isinstance(i, str)]
                for key in ('@graph', 'mainEntity', 'itemListElement'):
                    if key in node:
                        stack.append(node[key])
    return []
