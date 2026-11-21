import json
from pathlib import Path

from b2v.models import Brief, Script
from b2v.quality import check_script

BRIEF = Brief.from_dict(json.loads((Path(__file__).parents[1] / "examples" / "brief.json").read_text()))


def good_script(**over):
    d = dict(hook="Made for busy remote workers.",
             body=list(BRIEF.facts), cta=BRIEF.cta, caption="Lumen Coffee. Roasted within 48 hours.",
             hashtags=["#LumenCoffee"])
    d.update(over)
    return Script(**d)


def test_good_script_passes():
    assert check_script(good_script(), BRIEF).ok


def test_slop_is_rejected():
    r = check_script(good_script(hook="Unlock the game-changer for mornings"), BRIEF)
    assert not r.ok and any("slop" in i for i in r.issues)


def test_invented_number_is_rejected():
    r = check_script(good_script(body=["Roasted within 12 hours", "Free shipping over $40", "Cancel anytime"]), BRIEF)
    assert any("'12'" in i for i in r.issues)


def test_wordy_hook_is_rejected():
    r = check_script(good_script(hook="This is a very long hook that goes on and on for far too many words"), BRIEF)
    assert any("hook too long" in i for i in r.issues)


def test_too_few_scenes_rejected():
    r = check_script(good_script(body=["Only one scene"]), BRIEF)
    assert any("body must have" in i for i in r.issues)
