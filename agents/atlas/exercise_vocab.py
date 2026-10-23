"""
EXERCISE VOCABULARY (ATLAS, Phase 1 item 1.2c) - the words that appear INSIDE real exercise names.

This is REFERENCE DATA, not a rule list: it does not forbid or allow anything. It exists for one check. When the
local model drafts a training rule, every word and every example exercise name it uses must be made of words that
really appear in exercise names (squat, curl, jump, kettlebell, cable ...), or in names in Joey's own exercise
library. A CATEGORY word such as "explosive" or "exercise" is not an exercise-name word, so a rule built on it
would block nothing (found in a real run: the model wrote the rule words ["explosive"] AND made up examples
such as "explosive jump" so its own self-check passed). Such a draft is refused.

Deliberately NOT in the list: explosive, exercise, workout, move, heavy, light, hard, easy, careful, fast, intense.

Pure Python: no model, no network, no files. A missing word makes a draft get refused (the safe direction), and
the refusal tells him to use real exercise names; the starter rules do not depend on this list at all.
"""
import re

_WORDS = """
squat lunge deadlift press push pull row curl raise fly flye extension flexion crunch plank bridge thrust swing snatch clean
jerk jump hop bound skip throw slam toss carry walk run sprint climb climber crawl twist rotation rotate kickback pushdown
pulldown pullup chinup dip shrug situp sit stand step stepup kick flutter scissor bicycle russian woodchop chop lift hold hang
hinge good morning thruster burpee plyo plyometric jack skater shuffle stretch circle roll rock tuck pike arch
barbell dumbbell kettlebell cable machine band resistance loop smith ez bar trap hex landmine trx suspension ring rope battle
sled prowler ball medicine stability swiss bosu box bench rack plate chain bag sandbag tire wheel roller parallette handle strap
belt weighted vest bodyweight assisted free weight dumbbells barbells
incline decline flat seated lying prone supine kneeling kneel half tall single one two double alternating alternate arm leg
handed legged bent over overhead front back rear side lateral reverse wide close narrow grip neutral underhand overhand
supinated pronated hanging high low mid top bottom pause paused tempo slow drop cluster isometric static dynamic eccentric
concentric negative partial full deep split bulgarian sumo conventional romanian stiff straight curved floor wall air behind
head to and with on the of from in off up down out around across by per a an at
chest pec shoulder delt deltoid tricep bicep lat trap glute hamstring quad calf ab core oblique forearm wrist hip adductor
abductor groin neck spine rotator cuff rhomboid heel toe tibialis ankle finger knee elbow
goblet zottman hammer preacher concentration spider skull skullcrusher crusher tate guillotine arnold pallof copenhagen nordic
turkish get hyperextension hyper farmer suitcase waiter zercher jefferson bradford svend cuban scott larsen pendlay yates
kroc meadows seal helms jm bear crab inchworm handstand planche muscle dragon flag lever human
dead bug bird dog mountain hollow superman cobra cat camel child pigeon frog cossack curtsy curtsey clamshell fire hydrant
donkey monster march marching stair treadmill bike cycle rower erg elliptical swim swimming drag tug depth broad vertical star
power hang block board pin gripper pinch harness raises extensions push-up pull-up chin-up
military face chin crossover cross pullover stationary apart db bb kb pistol hack deck pec windmill windshield wiper
scapular retraction depression banded supported unsupported offset staggered elevated deficit feet foot hands hand heels toes
cyclist sissy crossbody assault ski spin pushup pullup situp chinup lying stagger
""".split()

KNOWN = frozenset(w.lower() for w in _WORDS)


def _plain(text) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split()) if isinstance(text, str) else ""


def _known(token: str, extra: frozenset) -> bool:
    """A token is known if it, or its singular, plural or -ing base form, is in the list or in `extra`."""
    pool = KNOWN | extra
    if token in pool or token.isdigit() or len(token) <= 1:           # single letters: "Farmer's" -> farmer s, "Y raise"
        return True
    forms = [token + "s", token + "es"]
    if token.endswith("s"):
        forms.append(token[:-1])
    if token.endswith("es"):
        forms.append(token[:-2])
    if token.endswith("ing") and len(token) > 5:
        base = token[:-3]
        forms += [base, base + "e"]
        if len(base) > 2 and base[-1] == base[-2]:            # running -> run
            forms.append(base[:-1])
    return any(f in pool for f in forms)


def tokens_of(names) -> frozenset:
    """Every word in a list of exercise names (used to count the names in Joey's own library as known words)."""
    out: set = set()
    if isinstance(names, list):
        for n in names:
            out.update(_plain(n).split())
    return frozenset(out)


def unknown_words(texts, extra_known: frozenset = frozenset()) -> list:
    """The words in `texts` (words, phrases or exercise names) that are not exercise-name words, in order, without repeats."""
    out: list = []
    for text in texts if isinstance(texts, list) else []:
        for token in _plain(text).split():
            if not _known(token, extra_known) and token not in out:
                out.append(token)
    return out