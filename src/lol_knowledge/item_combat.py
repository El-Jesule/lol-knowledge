"""Stateful and scenario-driven item combat mechanics for ``rotation.py``.

Covers items whose combat effects require specialized runtime state or scenario
inputs beyond generic single-component catalog triggers:

- **Direct combat passives (Block 1A):** 6610 Sundered Sky, 2502 Unending Despair,
  3084 Heartsteel, 3742 Dead Man's Plate, 3087 Statikk Shiv (Electroshock +
  multi-target Electrospark), 2512 Fiendhunter Bolts, 2523 Hexoptics C44,
  4628 Horizon Focus, 6695 Serpent's Fang, 3072 Bloodthirster (Ichor Shield),
  2517 Endless Hunger (Feast), 2520 Bastionbreaker (Sabotage).
- **Stackables, Tear transforms & consumables (Blocks 1B/1C):** 2139 Elixir of
  Sorcery, 2140 Elixir of Wrath, 2003/2031 Potions, 6657/3803 Eternity,
  3168 Senda inmortal (Now and Forever), 3121 Fimbulwinter (Everlasting),
  2530 Diadem of Songs (Consonance).
- **Support / ally-synergy items (Block 1D):** 3504 Ardent Censer, 6616 Staff of
  Flowing Water, 6620 Echoes of Helia, 4005 Imperial Mandate, 3870 Dream Maker,
  3876 Solstice Sleigh, 3109 Knight's Vow, 3137 Cryptbloom, 2524 Bandlepipes.

All numerical constants are verified against client 16.23 binary data
(``lol-knowledge/derived/item-effects.json`` and ``Global.wad.client``) and
Data Dragon 16.23.1.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .damage import DamageType, format_number
from .errors import RotationError, StatsError
from .runes import int_input
from .stats.data import ItemData
from .stats.labels import Label
from .stats.sheet import StatSheet

# Effects owned by StatSheet (inputs/consumables), ItemCombat, or DefenseSimulator so
# rotation.py does not emit generic "_skip" warnings or false Pending degradations.
SPECIALIZED_ITEM_EFFECTS: frozenset[tuple[str, str]] = frozenset(
    {
        # Handled in StatSheet
        ("3070", "manaflow"),
        ("3003", "manaflow"),
        ("3004", "manaflow"),
        ("3119", "manaflow"),
        ("2526", "manaflow"),
        ("1082", "glory"),
        ("3041", "glory"),
        ("6697", "eminence"),
        ("6657", "timeless"),
        ("3008", "murder"),
        ("3168", "murder"),
        ("2501", "retribution"),
        ("2138", "elixir-of-iron"),
        # Handled in ItemCombat (rotation.py)
        ("2139", "elixir-of-sorcery"),
        ("2140", "elixir-of-wrath"),
        ("2003", "consume"),
        ("2031", "consume"),
        ("6657", "eternity"),
        ("3803", "eternity"),
        ("3168", "now-and-forever"),
        ("3121", "everlasting"),
        ("2530", "consonance"),
        ("6610", "lightshield-strike"),
        ("2502", "anguish"),
        ("3084", "colossal-consumption"),
        ("3742", "shipwrecker"),
        ("3087", "electrospark"),
        ("3087", "electroshock"),
        ("2512", "opening-barrage"),
        ("2523", "magnification"),
        ("4628", "hypershot"),
        ("6695", "shield-reaver"),
        ("3072", "ichor-shield"),
        ("2517", "feast"),
        ("2520", "sabotage"),
        ("3504", "sanctify"),
        ("6616", "rapids"),
        ("6620", "soul-siphon"),
        ("4005", "order"),
        ("3870", "dream-maker"),
        ("3876", "going-sledding"),
        ("3109", "sacrifice"),
        ("3137", "life-from-death"),
        ("2524", "fanfare"),
        # Defense-only passives handled in defense.py
        ("1054", "enduring-focus"),
        ("3083", "warmogs-heart"),
        ("3026", "rebirth"),
    }
)

# Item actives that trigger ally heal/shield passives (Ardent, Staff, Helia, Dream Maker).
ALLY_HEAL_SHIELD_ACTIVES: frozenset[str] = frozenset({"3107", "3190", "3222"})
POTION_ITEMS: frozenset[str] = frozenset({"2003", "2031"})


@dataclass(frozen=True)
class ItemProc:
    """A damage proc emitted by ``ItemCombat`` for ``_Rotation`` to mitigate."""

    kind: str  # "item" | "on_hit" | "burn"
    source: str
    damage_type: DamageType
    raw: Fraction
    label: Label
    notes: tuple[str, ...] = ()
    apply_modifiers: bool = True
    targets_hit: int = 1
    aoe: bool = False
    life_steal: bool = False
    item_id: str = ""


@dataclass(frozen=True)
class ItemHeal:
    """A raw healing event emitted by ``ItemCombat``."""

    source: str
    raw: Fraction
    label: Label
    uses_hsp: bool = True
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemShield:
    """A raw shield event emitted by ``ItemCombat``."""

    source: str
    raw: Fraction
    label: Label
    duration: Fraction | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttackOverride:
    """Crit / bonus-damage / heal modifications applied to one basic attack."""

    crit_multiplier_override: Fraction | None = None
    bonus_true_damage_ratio: Fraction = Fraction(0)
    notes: tuple[str, ...] = ()
    labels: tuple[Label, ...] = ()
    heals: tuple[ItemHeal, ...] = ()
    extra_procs: tuple[ItemProc, ...] = ()


def _nonneg_input(inputs: Mapping[str, Fraction], key: str) -> Fraction | None:
    if key not in inputs:
        return None
    val = inputs[key]
    if val < 0:
        raise RotationError(f"input {key}: must not be negative, got {format_number(val)}")
    return val


def _statikk_bounces(level: int) -> int:
    """Client 16.23 BounceCount: 4 base, +1 at levels 6, 10, 14, 20."""
    bounces = 4
    for bp in (6, 10, 14, 20):
        if level >= bp:
            bounces += 1
    return bounces


def _bloodthirster_cap(level: int) -> Fraction:
    """Client 16.23 OvershieldCalc: 165 (L1-8), +15 per level at and after L9 (315 at L18)."""
    if level < 9:
        return Fraction(165)
    return Fraction(165 + 15 * (level - 8))


def _dream_maker_proc(level: int) -> Fraction:
    """Client 16.23 ProcDmg: 40 (L1-6), +10 per level at and after L7 (160 at L18)."""
    if level < 7:
        return Fraction(40)
    return Fraction(40 + 10 * (level - 6))


def _dream_maker_dr(level: int) -> Fraction:
    """Client 16.23 FlatDR: 50 (L1-6), +12 per level at and after L7 (194 at L18)."""
    if level < 7:
        return Fraction(50)
    return Fraction(50 + 12 * (level - 6))


def _solstice_sleigh_hp(level: int) -> Fraction:
    """Client 16.23 BonusHealthBuff: 50 (L1-6), +15 per level at and after L7 (230 at L18)."""
    if level < 7:
        return Fraction(50)
    return Fraction(50 + 15 * (level - 6))


def _helia_max_charges(level: int) -> Fraction:
    """Client 16.23 MaxCharges: 80 + 10 * (level - 1) (250 at L18)."""
    return Fraction(80 + 10 * max(0, level - 1))


class ItemCombat:
    """Runtime tracker for specialized Block 1 item mechanics in a rotation."""

    def __init__(
        self,
        sheet: StatSheet,
        items: Sequence[ItemData],
        target_kind: str | None,
        holder_range: str | None,
        inputs: Mapping[str, Fraction],
        timeline: bool,
        target_count: int = 1,
    ) -> None:
        self.sheet = sheet
        self.item_ids: frozenset[str] = frozenset(item.id for item in items)
        self.target_kind = target_kind
        self.holder_range = holder_range
        self.inputs = inputs
        self.timeline = timeline
        self.target_count = target_count

        self.notes: list[str] = []
        self.weakened = False
        self.speed_changed = False

        # Parsed optional scenario inputs
        try:
            self.target_impaired = int_input(inputs, "target_impaired", minimum=0, maximum=1)
            self.heartsteel_charged = int_input(inputs, "heartsteel_charged", minimum=0, maximum=1)
            self.hypershot_input = int_input(inputs, "hypershot", minimum=0, maximum=1)
            self.takedown_input = int_input(inputs, "takedown", minimum=0, maximum=1)
            self.sanctify_input = int_input(inputs, "sanctify_active", minimum=0, maximum=1)
            self.rapids_input = int_input(inputs, "rapids_active", minimum=0, maximum=1)
            self.dream_maker_input = int_input(inputs, "dream_maker_active", minimum=0, maximum=1)
            self.ally_present = int_input(inputs, "ally_present", minimum=0, maximum=1)
            self.ally_heal_trigger = int_input(inputs, "ally_heal_trigger", minimum=0, maximum=1)
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        self.target_distance = _nonneg_input(inputs, "target_distance")
        self.worthy_ally_damage = _nonneg_input(inputs, "worthy_ally_damage")
        self.attacker_hp_pct = _nonneg_input(inputs, "attacker_health_percent")
        if self.attacker_hp_pct is not None and self.attacker_hp_pct > 1:
            raise RotationError("input attacker_health_percent must be 0..1")

        # 6610 Sundered Sky
        self.sundered_ready = Fraction(0)
        self.sundered_used = False

        # 2502 Unending Despair (4 s periodic drain in combat)
        self.anguish_next = Fraction(4)
        self.anguish_used_no_tl = False

        # 3084 Heartsteel (3 s charge, 30 s CD)
        self.heartsteel_ready = Fraction(0)
        self.heartsteel_used = False

        # 3742 Dead Man's Plate (Momentum stacks, default 100 on first attack)
        mom = _nonneg_input(inputs, "momentum_stacks")
        if mom is not None and mom > 100:
            raise RotationError("input momentum_stacks must be 0..100")
        self.momentum_stacks = Fraction(100) if mom is None else mom

        # 3087 Statikk Shiv (Energized stacks: starts ready at 100, +15 per attack)
        self.statikk_stacks = 100 if "3087" in self.item_ids else 0

        # 2512 Fiendhunter Bolts (Opening Barrage: 3 attacks in 8 s after R, 45 s CD)
        self.barrage_charges = 0
        self.barrage_until: Fraction | None = None
        self.barrage_ready = Fraction(0)
        self.barrage_used = False

        # 4628 Horizon Focus (Hypershot +10% amp for 6 s)
        self.hypershot_until: Fraction | None = None
        self.hypershot_active = self.hypershot_input == 1
        self._hypershot_warned = False

        # 2523 Hexoptics C44
        self._magnification_warned = False

        # 6695 Serpent's Fang (Shield Reaver: 50% melee / 35% ranged for 3 s)
        self.shield_reaver_until: Fraction | None = None
        self.shield_reaver_applied = False

        # 3072 Bloodthirster (Ichor Shield accumulation)
        self.ichor_shield = Fraction(0)

        # 2517 Endless Hunger (Feast: +15% omnivamp for 8 s on takedown)
        self.feast_until: Fraction | None = None
        self.feast_active = self.takedown_input == 1

        # 2520 Bastionbreaker (Sabotage: true DoT vs structure/monster after takedown)
        self.sabotage_ready = self.takedown_input == 1

        # 2139 Elixir of Sorcery (+25 true damage, 5 s CD vs champs, no CD vs structures)
        self.sorcery_ready = Fraction(0)
        self.sorcery_used = False

        # 2003 / 2031 Potions
        self.potion_charges: dict[str, int] = {"2003": 1, "2031": 2}
        self.potion_end: Fraction | None = None
        self.potion_rate = Fraction(0)
        self.potion_source = ""
        self.potion_accrued = Fraction(0)

        # 6657 / 3803 Eternity (1 s CD)
        self.eternity_ready = Fraction(0)

        # 3121 Fimbulwinter (Everlasting: 8 s CD)
        self.fimbul_ready = Fraction(0)
        self.fimbul_used = False

        # 2530 Diadem of Songs (Consonance: 1 s interval in timeline)
        self.diadem_next = Fraction(1)

        # 3504 Ardent Censer / 6616 Staff of Flowing Water
        self.sanctify_until: Fraction | None = None
        self.sanctify_active = self.sanctify_input == 1
        self.rapids_until: Fraction | None = None
        self.rapids_active = self.rapids_input == 1

        # 6620 Echoes of Helia (Soul Siphon charges)
        self.helia_charges = Fraction(0)

        # 4005 Imperial Mandate (Order: +7% vulnerability for 4 s)
        self.mandate_until: Fraction | None = None
        self.mandate_active = False

        # 3870 Dream Maker (8 s CD, 3 s bubble)
        self.dream_ready = Fraction(0)
        self.dream_until: Fraction | None = None
        self.dream_proc_armed = self.dream_maker_input == 1

        # 3876 Solstice Sleigh (30 s CD)
        self.sleigh_ready = Fraction(0)
        self.sleigh_used = False

        # 3137 Cryptbloom (60 s CD)
        self.cryptbloom_ready = Fraction(0)
        self.cryptbloom_used = False

        # 2524 Bandlepipes (Fanfare: 8 s melee / 4 s ranged)
        self.fanfare_until: Fraction | None = None
        self.fanfare_active = False

    def _is_ranged(self) -> bool:
        return self.holder_range == "ranged"

    def _has_range(self, why: str) -> str:
        if self.holder_range is None:
            raise RotationError(f"{why}: needs --attacker-range melee|ranged")
        return self.holder_range

    # --- Dynamic combat stat bonuses (queried by _set_moment) ---

    def dynamic_bonus_as(self, clock: Fraction) -> Fraction:
        """Extra bonus AS fraction from Fiendhunter Bolts, Ardent Censer, and Bandlepipes."""
        total = Fraction(0)
        if (
            "2512" in self.item_ids
            and self.barrage_charges > 0
            and (
                not self.timeline or (self.barrage_until is not None and clock < self.barrage_until)
            )
        ):
            total += Fraction(50, 100)
        if "3504" in self.item_ids and self._is_sanctify_active(clock):
            total += Fraction(25, 100)
        if "2524" in self.item_ids and self._is_fanfare_active(clock):
            if self._is_ranged():
                total += Fraction(30, 100) * Fraction(667, 1000)
            else:
                total += Fraction(30, 100)
        return total

    def dynamic_bonus_ap(self, clock: Fraction) -> Fraction:
        """Extra flat AP from Staff of Flowing Water (Rapids: +40 AP for 6 s)."""
        if "6616" in self.item_ids and self._is_rapids_active(clock):
            return Fraction(40)
        return Fraction(0)

    def dynamic_bonus_ah(self, clock: Fraction) -> Fraction:
        """Extra flat AH from Staff of Flowing Water (Rapids: +15 AH for 6 s)."""
        if "6616" in self.item_ids and self._is_rapids_active(clock):
            return Fraction(15)
        return Fraction(0)

    def dynamic_bonus_flat_ms(self, clock: Fraction) -> Fraction:
        """Extra flat MS from Bandlepipes Fanfare (+20 MS)."""
        if "2524" in self.item_ids and self._is_fanfare_active(clock):
            return Fraction(20)
        return Fraction(0)

    def dynamic_bonus_omnivamp(self, clock: Fraction) -> Fraction:
        """Extra omnivamp fraction from 2517 Endless Hunger Feast (+15% for 8 s)."""
        if "2517" not in self.item_ids:
            return Fraction(0)
        if not self.timeline:
            return Fraction(15, 100) if self.feast_active else Fraction(0)
        if self.feast_until is not None and clock < self.feast_until:
            return Fraction(15, 100)
        return Fraction(0)

    def _is_sanctify_active(self, clock: Fraction) -> bool:
        if self.sanctify_input == 1:
            return True
        if not self.timeline:
            return self.sanctify_active
        return self.sanctify_until is not None and clock < self.sanctify_until

    def _is_rapids_active(self, clock: Fraction) -> bool:
        if self.rapids_input == 1:
            return True
        if not self.timeline:
            return self.rapids_active
        return self.rapids_until is not None and clock < self.rapids_until

    def _is_fanfare_active(self, clock: Fraction) -> bool:
        if not self.timeline:
            return self.fanfare_active
        return self.fanfare_until is not None and clock < self.fanfare_until

    def _is_hypershot_active(self, clock: Fraction) -> bool:
        if self.hypershot_input == 1:
            return True
        if not self.timeline:
            return self.hypershot_active
        return self.hypershot_until is not None and clock < self.hypershot_until

    def _is_mandate_active(self, clock: Fraction) -> bool:
        if not self.timeline:
            return self.mandate_active
        return self.mandate_until is not None and clock < self.mandate_until

    # --- Damage modifiers (dealt & taken) ---

    def dealt_modifier(
        self, part_kind: str, clock: Fraction, *, slot: str | None = None
    ) -> tuple[Fraction, list[Label], list[str]]:
        """Additive dealt damage percent bonus (as fraction, e.g. 0.10 for +10%)."""
        bonus = Fraction(0)
        labels: list[Label] = []
        notes: list[str] = []

        # 3168 Senda inmortal (Now and Forever: >50% HP -> +4% damage dealt)
        if (
            "3168" in self.item_ids
            and self.attacker_hp_pct is not None
            and self.attacker_hp_pct > Fraction(1, 2)
        ):
            bonus += Fraction(4, 100)
            labels.append(Label.OFFICIAL)
            notes.append("3168 now-and-forever (+4% damage above 50% HP)")

        # 2523 Hexoptics C44 (Magnification: 0..10% linear on basic attacks up to 500 range)
        if "2523" in self.item_ids and part_kind == "attack":
            if self.target_distance is None:
                if not self._magnification_warned:
                    self._magnification_warned = True
                    self.notes.append(
                        "2523 magnification: needs --input target_distance=<units> (0..500)"
                    )
                    self.weakened = True
            elif self.target_distance > 0:
                ratio = min(self.target_distance, Fraction(500)) / Fraction(500)
                amp = ratio * Fraction(10, 100)
                bonus += amp
                labels.append(Label.DERIVED)
                notes.append(
                    f"2523 magnification (+{format_number(amp * 100)}% at "
                    f"{format_number(self.target_distance)} range)"
                )

        # 4628 Horizon Focus (Hypershot: +10% damage to champions revealed from >=600 range)
        if "4628" in self.item_ids and self.target_kind == "champion":
            # The triggering ability itself benefits from Hypershot if >=600 range.
            if (
                part_kind == "ability"
                and self.target_distance is not None
                and self.target_distance >= 600
            ):
                self.hypershot_active = True
                if self.timeline:
                    self.hypershot_until = clock + 6
            if self._is_hypershot_active(clock):
                bonus += Fraction(10, 100)
                labels.append(Label.DERIVED)
                notes.append("4628 hypershot (+10% damage to revealed champion)")
            elif (
                part_kind == "ability"
                and self.target_distance is None
                and self.hypershot_input is None
                and not self._hypershot_warned
            ):
                self._hypershot_warned = True
                self.notes.append(
                    "4628 hypershot: needs --input target_distance=<units> or hypershot=0|1"
                )
                self.weakened = True

        # 4005 Imperial Mandate (Order: +7% vulnerability on immobilized champion for 4 s)
        if "4005" in self.item_ids and self.target_kind == "champion":
            if self.target_impaired == 1 and part_kind == "ability":
                self.mandate_active = True
                if self.timeline:
                    self.mandate_until = clock + 4
            if self._is_mandate_active(clock):
                bonus += Fraction(7, 100)
                labels.append(Label.OFFICIAL)
                notes.append("4005 order (+7% vulnerability on immobilized champion)")

        return bonus, labels, notes

    # --- Potion actives (item:2003 / item:2031) ---

    def is_potion_active(self, item_id: str) -> bool:
        return item_id in POTION_ITEMS and item_id in self.item_ids

    def cast_potion(self, item_id: str, clock: Fraction) -> tuple[str, list[ItemHeal]]:
        """Drink a Health Potion (2003) or Refillable Potion (2031)."""
        if item_id not in self.item_ids:
            raise RotationError(f"item:{item_id} is not equipped")
        left = self.potion_charges.get(item_id, 0)
        if left <= 0:
            raise RotationError(f"item:{item_id} has no charges left")
        self.potion_charges[item_id] = left - 1
        if item_id == "2003":
            total_heal, dur = Fraction(120), Fraction(15)
            name = "item:2003 (Poción de vida)"
        else:
            total_heal, dur = Fraction(100), Fraction(12)
            name = "item:2031 (Poción reutilizable)"
        if not self.timeline:
            return name, [
                ItemHeal(
                    f"{item_id} consume",
                    total_heal,
                    Label.OFFICIAL,
                    uses_hsp=False,
                    notes=(f"{format_number(total_heal)} HP over {format_number(dur)} s",),
                )
            ]
        # In timeline mode, queue/extend continuous regeneration accrued across steps/waits.
        self.potion_rate = total_heal / dur
        self.potion_source = f"{item_id} consume"
        self.potion_end = (
            max(self.potion_end, clock) + dur if self.potion_end is not None else clock + dur
        )
        self.potion_accrued = clock
        return name, []

    def accrue_potion(self, until: Fraction) -> list[ItemHeal]:
        """Accrue active potion HoT up to ``until`` in timeline mode."""
        if not self.timeline or self.potion_end is None or until <= self.potion_accrued:
            return []
        end = min(until, self.potion_end)
        if end <= self.potion_accrued:
            return []
        raw = self.potion_rate * (end - self.potion_accrued)
        start = self.potion_accrued
        self.potion_accrued = end
        if end >= self.potion_end:
            self.potion_end = None
            self.potion_rate = Fraction(0)
        return [
            ItemHeal(
                f"{self.potion_source} ({format_number(start)}-{format_number(end)} s)",
                raw,
                Label.OFFICIAL,
                uses_hsp=False,
            )
        ]

    # --- Ally heal/shield trigger (for 3504, 6616, 6620, 3870) ---

    def on_ally_heal_or_shield(self, clock: Fraction) -> list[ItemHeal]:
        """Activate Ardent/Staff/Dream Maker and discharge Echoes of Helia charges."""
        heals: list[ItemHeal] = []
        if "3504" in self.item_ids:
            self.sanctify_active = True
            if self.timeline:
                self.sanctify_until = clock + 6
            self.speed_changed = True
        if "6616" in self.item_ids:
            self.rapids_active = True
            if self.timeline:
                self.rapids_until = clock + 6
        if "3870" in self.item_ids:
            can_dream = (
                (clock >= self.dream_ready) if self.timeline else (not self.dream_proc_armed)
            )
            if can_dream:
                self.dream_proc_armed = True
                if self.timeline:
                    self.dream_until = clock + 3
                    self.dream_ready = clock + 8
        if "6620" in self.item_ids and self.helia_charges > 0:
            raw = self.helia_charges
            self.helia_charges = Fraction(0)
            heals.append(
                ItemHeal(
                    "6620 soul-siphon (ally heal)",
                    raw,
                    Label.DERIVED,
                    uses_hsp=True,
                    notes=("consumed stored Soul Charges (100% conversion)",),
                )
            )
        return heals

    # --- Basic attack hook (6610, 2512, 3084, 3742, 3087, 3504, 2520) ---

    def on_attack(
        self,
        *,
        step_crit: bool,
        normal_crit_multiplier: Fraction | None,
        clock: Fraction,
        attacker_hp: Fraction | None,
        attacker_max_hp: Fraction | None,
    ) -> AttackOverride:
        """Evaluate specialized attack-time passives (Sundered Sky, Fiendhunter, Heartsteel...)."""
        crit_override: Fraction | None = None
        bonus_true_ratio = Fraction(0)
        notes: list[str] = []
        labels: list[Label] = []
        heals: list[ItemHeal] = []
        procs: list[ItemProc] = []

        # 1. 6610 Sundered Sky (Lightshield Strike: 10 s CD per target vs champion)
        if "6610" in self.item_ids and self.target_kind == "champion":
            can_proc = (clock >= self.sundered_ready) if self.timeline else (not self.sundered_used)
            if can_proc:
                self.sundered_used = True
                if self.timeline:
                    self.sundered_ready = clock + 10
                if not step_crit and normal_crit_multiplier is not None:
                    crit_override = normal_crit_multiplier * Fraction(80, 100)
                    labels.append(Label.DERIVED)
                    notes.append(
                        f"6610 lightshield-strike: forced crit at 80% crit damage "
                        f"({format_number(crit_override)}x)"
                    )
                base_ad = self.sheet["attack_damage"].scoped("base")
                ranged_mod = Fraction(1, 2) if self._is_ranged() else Fraction(1)
                missing_hp = Fraction(0)
                heal_notes = [f"90% base AD ({format_number(base_ad)})"]
                if self._is_ranged():
                    heal_notes.append("x0.5 ranged")
                if attacker_hp is not None and attacker_max_hp is not None:
                    missing_hp = max(Fraction(0), attacker_max_hp - attacker_hp)
                    if missing_hp > 0:
                        heal_notes.append(f"+ 4% missing HP ({format_number(missing_hp)})")
                else:
                    heal_notes.append("0 missing HP assumed (pass --input attacker_health_percent)")
                raw_heal = base_ad * Fraction(90, 100) * ranged_mod + missing_hp * Fraction(4, 100)
                heals.append(
                    ItemHeal(
                        "6610 lightshield-strike",
                        raw_heal,
                        Label.DERIVED,
                        uses_hsp=True,
                        notes=tuple(heal_notes),
                    )
                )

        # 2. 2512 Fiendhunter Bolts (Opening Barrage: 3 attacks in 8 s after R)
        if "2512" in self.item_ids and self.barrage_charges > 0:
            active_barrage = not self.timeline or (
                self.barrage_until is not None and clock <= self.barrage_until
            )
            if active_barrage:
                self.barrage_charges -= 1
                if self.barrage_charges == 0:
                    self.speed_changed = True
                if step_crit:
                    bonus_true_ratio = Fraction(15, 100)
                    labels.append(Label.OFFICIAL)
                    notes.append("2512 opening-barrage: +15% bonus true damage on natural crit")
                elif normal_crit_multiplier is not None:
                    cand = normal_crit_multiplier * Fraction(80, 100)
                    if crit_override is None or cand > crit_override:
                        crit_override = cand
                    labels.append(Label.OFFICIAL)
                    notes.append(
                        f"2512 opening-barrage: forced crit at 80% crit damage "
                        f"({format_number(cand)}x)"
                    )

        # 3. 3084 Heartsteel (Colossal Consumption: 3 s charge, 30 s CD vs champion)
        if "3084" in self.item_ids and self.target_kind == "champion":
            charged = self.heartsteel_charged == 1 or (self.timeline and clock >= 3)
            can_proc = (
                (clock >= self.heartsteel_ready) if self.timeline else (not self.heartsteel_used)
            )
            if charged and can_proc:
                self.heartsteel_used = True
                if self.timeline:
                    self.heartsteel_ready = clock + 30
                max_hp = self.sheet["health"].total()
                raw = Fraction(70) + max_hp * Fraction(6, 100)
                perm_hp = raw * Fraction(10, 100)
                procs.append(
                    ItemProc(
                        kind="item",
                        source="3084 colossal-consumption (Consumo colosal)",
                        damage_type=DamageType.PHYSICAL,
                        raw=raw,
                        label=Label.OFFICIAL,
                        notes=(
                            f"70 + 6% max HP ({format_number(max_hp)}); "
                            f"grants +{format_number(perm_hp)} permanent max HP",
                        ),
                        item_id="3084",
                    )
                )
            elif not charged and self.heartsteel_charged is None and not self.timeline:
                self.notes.append(
                    "3084 colossal-consumption: needs 3 s charge (--timeline or "
                    "--input heartsteel_charged=1)"
                )

        # 4. 3742 Dead Man's Plate (Shipwrecker: discharge Momentum stacks)
        if "3742" in self.item_ids and self.momentum_stacks > 0:
            stacks = self.momentum_stacks
            self.momentum_stacks = Fraction(0)
            base_ad = self.sheet["attack_damage"].scoped("base")
            frac = stacks / Fraction(100)
            raw = stacks * Fraction(4, 10) + base_ad * frac
            procs.append(
                ItemProc(
                    kind="item",
                    source="3742 shipwrecker (Naufragio)",
                    damage_type=DamageType.PHYSICAL,
                    raw=raw,
                    label=Label.DERIVED,
                    notes=(
                        f"{format_number(stacks)} Momentum stacks "
                        f"({format_number(stacks * Fraction(4, 10))} + "
                        f"{format_number(frac * 100)}% base AD)",
                    ),
                    item_id="3742",
                )
            )

        # 5. 3087 Statikk Shiv (Electrospark + Electroshock: Energized chain lightning)
        if "3087" in self.item_ids:
            if self.statikk_stacks >= 100:
                self.statikk_stacks = 0
                is_non_champ = self.target_kind in {"minion", "monster"}
                raw = Fraction(90) if is_non_champ else Fraction(60)
                max_bounces = _statikk_bounces(self.sheet.level)
                hits = min(self.target_count, max_bounces)
                procs.append(
                    ItemProc(
                        kind="on_hit",
                        source="3087 electrospark (Electrochispa)",
                        damage_type=DamageType.MAGIC,
                        raw=raw,
                        label=Label.DERIVED,
                        notes=(
                            f"Energized lightning bounces to {hits}/{max_bounces} targets "
                            f"({'non-champion 90' if is_non_champ else 'champion 60'})",
                        ),
                        targets_hit=hits,
                        aoe=hits > 1,
                        item_id="3087",
                    )
                )
            else:
                # 6 base Energized per attack + 9 from Electroshock = 15 per attack
                self.statikk_stacks = min(100, self.statikk_stacks + 15)

        # 6. 3504 Ardent Censer (Sanctify: +20 magic on-hit when active)
        if "3504" in self.item_ids and self._is_sanctify_active(clock):
            procs.append(
                ItemProc(
                    kind="on_hit",
                    source="3504 sanctify (Santificar)",
                    damage_type=DamageType.MAGIC,
                    raw=Fraction(20),
                    label=Label.OFFICIAL,
                    notes=("+20 magic damage on-hit while Sanctify is active",),
                    item_id="3504",
                )
            )

        # 7. 2520 Bastionbreaker (Sabotage: 300 + 25 * lethality [x0.8 ranged] true DoT vs
        # structure/monster after champion takedown)
        if (
            "2520" in self.item_ids
            and self.sabotage_ready
            and self.target_kind in {"structure", "monster"}
        ):
            self.sabotage_ready = False
            leth = self.sheet["lethality"].total()
            mult = Fraction(8, 10) if self._is_ranged() else Fraction(1)
            raw = (Fraction(300) + Fraction(25) * leth) * mult
            procs.append(
                ItemProc(
                    kind="burn",
                    source="2520 sabotage (Sabotaje, 3 s DoT)",
                    damage_type=DamageType.TRUE,
                    raw=raw,
                    label=Label.DERIVED,
                    notes=(
                        f"300 + 25x lethality ({format_number(leth)}) over 3 s"
                        + (" x0.8 ranged" if self._is_ranged() else ""),
                    ),
                    item_id="2520",
                )
            )

        return AttackOverride(
            crit_multiplier_override=crit_override,
            bonus_true_damage_ratio=bonus_true_ratio,
            notes=tuple(notes),
            labels=tuple(labels),
            heals=tuple(heals),
            extra_procs=tuple(procs),
        )

    # --- Cast hook (2512 R trigger, 6657/3803 Eternity) ---

    def on_cast(self, slot: str, mana_spent: Fraction, clock: Fraction) -> list[ItemHeal]:
        """Handle cast-triggered passives (Fiendhunter R, Eternity mana->HP)."""
        heals: list[ItemHeal] = []
        if "2512" in self.item_ids and slot == "R":
            can_proc = (clock >= self.barrage_ready) if self.timeline else (not self.barrage_used)
            if can_proc:
                self.barrage_used = True
                self.barrage_charges = 3
                self.speed_changed = True
                if self.timeline:
                    self.barrage_until = clock + 8
                    self.barrage_ready = clock + 45

        if ({"6657", "3803"} & self.item_ids) and mana_spent > 0:
            can_proc = (not self.timeline) or (clock >= self.eternity_ready)
            if can_proc:
                if self.timeline:
                    self.eternity_ready = clock + 1
                raw = min(Fraction(20), mana_spent * Fraction(25, 100))
                iid = "6657" if "6657" in self.item_ids else "3803"
                heals.append(
                    ItemHeal(
                        f"{iid} eternity",
                        raw,
                        Label.OFFICIAL,
                        uses_hsp=True,
                        notes=(f"25% of {format_number(mana_spent)} mana spent (cap 20)",),
                    )
                )
        return heals

    # --- Post-step damage/takedown/CC hooks ---

    def on_damage_dealt(
        self,
        *,
        pre_mitigation_total: Fraction,
        post_mitigation_physical: Fraction,
        clock: Fraction,
        current_mana: Fraction | None,
    ) -> tuple[list[ItemProc], list[ItemHeal], list[ItemShield], Fraction]:
        """Handle on-damage item procs, Shield Reaver shred ratio, Helia, Elixir, Fimbulwinter.

        Returns ``(procs, heals, shields, shield_shred_ratio)`` where
        ``shield_shred_ratio`` is ``0`` or ``0.5``/``0.35`` on the first application of
        6695 Serpent's Fang.
        """
        procs: list[ItemProc] = []
        heals: list[ItemHeal] = []
        shields: list[ItemShield] = []
        shred_ratio = Fraction(0)

        # 2139 Elixir of Sorcery (+25 true damage vs champion [5 s CD] or structure [no CD])
        if (
            "2139" in self.item_ids
            and self.sheet.level >= 9
            and self.target_kind in {"champion", "structure"}
        ):
            if self.target_kind == "structure":
                can_sorc = True
            else:
                can_sorc = (
                    (clock >= self.sorcery_ready) if self.timeline else (not self.sorcery_used)
                )
            if can_sorc:
                if self.target_kind == "champion":
                    self.sorcery_used = True
                    if self.timeline:
                        self.sorcery_ready = clock + 5
                procs.append(
                    ItemProc(
                        kind="item",
                        source="2139 elixir-of-sorcery",
                        damage_type=DamageType.TRUE,
                        raw=Fraction(25),
                        label=Label.OFFICIAL,
                        notes=("+25 bonus true damage vs champion/turret",),
                        apply_modifiers=False,
                        item_id="2139",
                    )
                )

        # 2140 Elixir of Wrath (+12% physical vamp vs champions)
        if (
            "2140" in self.item_ids
            and self.sheet.level >= 9
            and self.target_kind == "champion"
            and post_mitigation_physical > 0
        ):
            raw = post_mitigation_physical * Fraction(12, 100)
            heals.append(
                ItemHeal(
                    "2140 elixir-of-wrath (physical vamp)",
                    raw,
                    Label.OFFICIAL,
                    uses_hsp=False,
                    notes=(f"12% of {format_number(post_mitigation_physical)} physical damage",),
                )
            )

        # 6695 Serpent's Fang (Shield Reaver: 50% melee / 35% ranged for 3 s)
        if "6695" in self.item_ids and self.target_kind == "champion":
            active_shred = (
                (self.shield_reaver_until is not None and clock < self.shield_reaver_until)
                if self.timeline
                else self.shield_reaver_applied
            )
            if not active_shred:
                shred_ratio = Fraction(35, 100) if self._is_ranged() else Fraction(50, 100)
                self.shield_reaver_applied = True
                if self.timeline:
                    self.shield_reaver_until = clock + 3
                self.notes.append(
                    "6695 shield-reaver: reduced target shield by "
                    f"{format_number(shred_ratio * 100)}% (3 s)"
                )

        # 6620 Echoes of Helia (store 30% of pre-mitigation champ damage up to MaxCharges)
        if "6620" in self.item_ids and self.target_kind == "champion" and pre_mitigation_total > 0:
            cap = _helia_max_charges(self.sheet.level)
            self.helia_charges = min(
                cap, self.helia_charges + pre_mitigation_total * Fraction(3, 10)
            )
            if self.ally_heal_trigger == 1 and self.helia_charges >= 10:
                heals.extend(self.on_ally_heal_or_shield(clock))

        # 3870 Dream Maker (purple bubble: bonus magic damage on next attack/ability)
        if "3870" in self.item_ids and self.dream_proc_armed:
            valid = not self.timeline or (self.dream_until is None or clock <= self.dream_until)
            if valid:
                self.dream_proc_armed = False
                raw = _dream_maker_proc(self.sheet.level)
                procs.append(
                    ItemProc(
                        kind="item",
                        source="3870 dream-maker (purple bubble)",
                        damage_type=DamageType.MAGIC,
                        raw=raw,
                        label=Label.DERIVED,
                        notes=(f"Dream Maker bonus magic damage at level {self.sheet.level}",),
                        item_id="3870",
                    )
                )

        # 3121 Fimbulwinter (Everlasting: shield on immobilize/melee slow, 8 s CD)
        if "3121" in self.item_ids and self.target_kind == "champion" and self.target_impaired == 1:
            can_f = (clock >= self.fimbul_ready) if self.timeline else (not self.fimbul_used)
            if can_f:
                self.fimbul_used = True
                if self.timeline:
                    self.fimbul_ready = clock + 8
                mana_val = (
                    current_mana
                    if current_mana is not None
                    else (
                        self.sheet["mana"].total()
                        if self.sheet["mana"].status == "resolved"
                        else Fraction(0)
                    )
                )
                raw = Fraction(100) + mana_val * Fraction(45, 1000)
                sh_notes = [f"100 + 4.5% current mana ({format_number(mana_val)})"]
                if self.target_count > 1:
                    raw *= Fraction(18, 10)
                    sh_notes.append("+80% (>1 nearby enemy)")
                shields.append(
                    ItemShield(
                        "3121 everlasting",
                        raw,
                        Label.DERIVED,
                        duration=Fraction(3),
                        notes=tuple(sh_notes),
                    )
                )

        # 3876 Solstice Sleigh (Going Sledding: 30 s CD on slow/immobilize with ally)
        if (
            "3876" in self.item_ids
            and self.target_kind == "champion"
            and self.target_impaired == 1
            and self.ally_present == 1
        ):
            can_s = (clock >= self.sleigh_ready) if self.timeline else (not self.sleigh_used)
            if can_s:
                self.sleigh_used = True
                if self.timeline:
                    self.sleigh_ready = clock + 30
                raw = _solstice_sleigh_hp(self.sheet.level)
                heals.append(
                    ItemHeal(
                        "3876 going-sledding",
                        raw,
                        Label.DERIVED,
                        uses_hsp=False,
                        notes=(
                            f"bonus HP/heal at level {self.sheet.level} (+20% decaying MS 2.5 s)",
                        ),
                    )
                )

        # 2524 Bandlepipes (Fanfare: +20 MS and +30%/+20% AS aura for 8 s melee / 4 s ranged)
        if "2524" in self.item_ids and self.target_kind == "champion" and self.target_impaired == 1:
            self.fanfare_active = True
            self.speed_changed = True
            if self.timeline:
                dur = Fraction(4) if self._is_ranged() else Fraction(8)
                self.fanfare_until = clock + dur

        # 2502 Unending Despair without timeline (fires once on first champ damage)
        if (
            "2502" in self.item_ids
            and not self.timeline
            and self.target_kind == "champion"
            and not self.anguish_used_no_tl
        ):
            self.anguish_used_no_tl = True
            bonus_hp = self.sheet["health"].scoped("bonus")
            raw = bonus_hp * Fraction(3, 100)
            if raw > 0:
                procs.append(
                    ItemProc(
                        kind="item",
                        source="2502 anguish (Angustia)",
                        damage_type=DamageType.MAGIC,
                        raw=raw,
                        label=Label.DERIVED,
                        notes=(
                            f"3% bonus HP ({format_number(bonus_hp)}); heals 250% of damage dealt "
                            "(once without --timeline)",
                        ),
                        targets_hit=self.target_count,
                        aoe=True,
                        item_id="2502",
                    )
                )

        return procs, heals, shields, shred_ratio

    def on_takedown(self, clock: Fraction) -> list[ItemHeal]:
        """Handle champion-kill item effects (2517 Feast, 2520 Sabotage, 3137 Cryptbloom)."""
        heals: list[ItemHeal] = []
        if self.target_kind != "champion":
            return heals
        if "2517" in self.item_ids:
            self.feast_active = True
            if self.timeline:
                self.feast_until = clock + 8
            self.notes.append("2517 feast: +15% omnivamp for 8 s on takedown")
        if "2520" in self.item_ids:
            self.sabotage_ready = True
            self.notes.append("2520 sabotage: empowered next attack vs structure/epic monster")
        if "3137" in self.item_ids:
            can_c = (
                (clock >= self.cryptbloom_ready) if self.timeline else (not self.cryptbloom_used)
            )
            if can_c:
                self.cryptbloom_used = True
                if self.timeline:
                    self.cryptbloom_ready = clock + 60
                ap = self.sheet["ability_power"].total()
                raw = Fraction(100) + ap * Fraction(20, 100)
                heals.append(
                    ItemHeal(
                        "3137 life-from-death",
                        raw,
                        Label.DERIVED,
                        uses_hsp=True,
                        notes=(f"100 + 20% AP ({format_number(ap)}) healing nova on takedown",),
                    )
                )
        return heals

    def on_bloodthirster_overheal(self, excess_life_steal: Fraction) -> ItemShield | None:
        """Convert excess life steal above max HP into Bloodthirster's Ichor Shield (3072)."""
        if "3072" not in self.item_ids or excess_life_steal <= 0:
            return None
        cap = _bloodthirster_cap(self.sheet.level)
        gain = min(excess_life_steal, max(Fraction(0), cap - self.ichor_shield))
        if gain <= 0:
            return None
        self.ichor_shield += gain
        return ItemShield(
            "3072 ichor-shield",
            gain,
            Label.DERIVED,
            duration=Fraction(25),
            notes=(
                f"excess life steal converted to shield (cap {format_number(cap)} at "
                f"level {self.sheet.level})",
            ),
        )

    def knights_vow_heal(self) -> list[ItemHeal]:
        """3109 Knight's Vow: heal 12% of worthy ally's champion damage (via --input)."""
        if "3109" not in self.item_ids or self.worthy_ally_damage is None:
            return []
        if self.worthy_ally_damage <= 0:
            return []
        raw = self.worthy_ally_damage * Fraction(12, 100)
        return [
            ItemHeal(
                "3109 sacrifice (ally damage heal)",
                raw,
                Label.OFFICIAL,
                uses_hsp=False,
                notes=(f"12% of worthy ally damage ({format_number(self.worthy_ally_damage)})",),
            )
        ]

    # --- Periodic timeline triggers (2502 Unending Despair every 4 s, 2530 Diadem every 1 s) ---

    def periodic_split_times(self, start: Fraction, until: Fraction) -> list[Fraction]:
        """Exact timestamps in (start, until] where periodic item triggers fire."""
        if not self.timeline:
            return []
        pts: list[Fraction] = []
        if "2502" in self.item_ids and self.target_kind == "champion":
            t = self.anguish_next
            while t <= until:
                if t > start:
                    pts.append(t)
                t += 4
        if "2530" in self.item_ids and self.target_kind == "champion":
            t = self.diadem_next
            while t <= until:
                if t > start:
                    pts.append(t)
                t += 1
        if self.potion_end is not None and start < self.potion_end <= until:
            pts.append(self.potion_end)
        return pts

    def pop_periodic(self, at: Fraction) -> tuple[list[ItemProc], list[ItemHeal]]:
        """Fire any periodic item effects due at timestamp ``at``."""
        procs: list[ItemProc] = []
        heals: list[ItemHeal] = []
        if not self.timeline:
            return procs, heals
        if "2502" in self.item_ids and self.target_kind == "champion":
            while self.anguish_next <= at:
                t = self.anguish_next
                self.anguish_next += 4
                bonus_hp = self.sheet["health"].scoped("bonus")
                raw = bonus_hp * Fraction(3, 100)
                if raw > 0:
                    procs.append(
                        ItemProc(
                            kind="item",
                            source=f"2502 anguish (Angustia at {format_number(t)} s)",
                            damage_type=DamageType.MAGIC,
                            raw=raw,
                            label=Label.DERIVED,
                            notes=(f"3% bonus HP ({format_number(bonus_hp)}); heals 250% dealt",),
                            targets_hit=self.target_count,
                            aoe=True,
                            item_id="2502",
                        )
                    )
        if "2530" in self.item_ids and self.target_kind == "champion":
            while self.diadem_next <= at:
                t = self.diadem_next
                self.diadem_next += 1
                if self.sheet["mana"].status == "resolved":
                    max_mana = self.sheet["mana"].total()
                    raw = max_mana * Fraction(8, 1000)
                    if raw > 0:
                        heals.append(
                            ItemHeal(
                                f"2530 consonance (ally heal at {format_number(t)} s)",
                                raw,
                                Label.DERIVED,
                                uses_hsp=True,
                                notes=(f"0.8% max mana ({format_number(max_mana)})/s",),
                            )
                        )
        heals.extend(self.accrue_potion(at))
        return procs, heals

    def has_periodic_due(self, until: Fraction) -> bool:
        if not self.timeline:
            return False
        if (
            "2502" in self.item_ids
            and self.target_kind == "champion"
            and self.anguish_next <= until
        ):
            return True
        if "2530" in self.item_ids and self.target_kind == "champion" and self.diadem_next <= until:
            return True
        return bool(
            self.potion_end is not None and self.potion_accrued < min(until, self.potion_end)
        )
