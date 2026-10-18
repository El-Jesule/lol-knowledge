"""Manually transcribed wiki evidence for comparison only.

This module is not an automated wiki client: the wiki API returned 403 during
the investigation. Values were read from the rendered page on 2026-10-18.
Licence: CC BY-SA 3.0. See evidence/usage-conditions.md.
"""

from __future__ import annotations

WIKI_URL = "https://wiki.leagueoflegends.com/en-us/Zaahen?oldid=4050539"
WIKI_ACCESSED = "2026-10-18"
WIKI_LAST_EDITED = "2026-08-07"
WIKI_LICENSE = "CC BY-SA 3.0"

WIKI_VALUES: dict[str, tuple[float, ...]] = {
    "q.first_hit_base_damage": (15.0, 30.0, 45.0, 60.0, 75.0),
    "q.recast_base_damage": (30.0, 60.0, 90.0, 120.0, 150.0),
    "q.bonus_ad_ratio": (0.20, 0.25, 0.30, 0.35, 0.40),
    "q.monster_damage_multiplier": (2.0,),
    "q.cooldown_seconds": (10.0, 9.0, 8.0, 7.0, 6.0),
    "q.heal_percent_max_hp": (0.05, 0.06, 0.07, 0.08, 0.09),
    "q.knockup_seconds": (0.75,),
    "q.mana_cost": (25.0,),
    "w.initial_base_damage": (40.0, 60.0, 80.0, 100.0, 120.0),
    "w.secondary_base_damage": (30.0, 50.0, 70.0, 90.0, 110.0),
    "w.cooldown_seconds": (14.0, 13.5, 13.0, 12.5, 12.0),
    "w.mana_cost": (50.0,),
    "e.base_damage": (40.0, 60.0, 80.0, 100.0, 120.0),
    "e.percent_max_hp_magic": (0.04, 0.045, 0.05, 0.055, 0.06),
    "e.cooldown_seconds": (10.0, 9.5, 9.0, 8.5, 8.0),
    "e.mana_cost": (40.0,),
    "r.base_damage": (250.0, 400.0, 550.0),
    "r.bonus_ad_ratio": (2.0,),
    "r.armor_penetration": (0.10, 0.20, 0.30),
    "r.heal_fraction": (0.33,),
    "r.damage_reduction": (0.5,),
    "r.cooldown_seconds": (110.0, 95.0, 80.0),
    "r.mana_cost": (100.0,),
    "passive.ad_per_stack_min": (0.015,),
    "passive.ad_per_stack": (2.95,),
    "passive.max_stacks": (12.0,),
    "champion.attack_damage_per_level": (4.0,),
}

# The wiki's own patch history documents 2.8 %, contradicting its summary.
WIKI_PATCH_HISTORY_AD_PER_STACK = (2.8,)
