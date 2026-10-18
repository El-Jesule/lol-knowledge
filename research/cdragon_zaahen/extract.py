"""Extract a small, auditable subset of Zaahen spell data from a CDragon bin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .provenance import Provenance, Status, combine_statuses

CHAMPION = "Zaahen"
PASSIVE_PATH = "Characters/Zaahen/Spells/ZaahenPassiveAbility/ZaahenPassive"
ROOT_PATH = "Characters/Zaahen/CharacterRecords/Root"
Q_PATH = "Characters/Zaahen/Spells/ZaahenQAbility/ZaahenQ"
W_PATH = "Characters/Zaahen/Spells/ZaahenWAbility/ZaahenW"
E_PATH = "Characters/Zaahen/Spells/ZaahenEAbility/ZaahenE"
R_PATH = "Characters/Zaahen/Spells/ZaahenRAbility/ZaahenR"

KNOWN_PART_TYPES = frozenset(
    {
        "NamedDataValueCalculationPart",
        "StatByNamedDataValueCalculationPart",
        "StatByCoefficientCalculationPart",
        "GameCalculationModified",
    }
)


class ExtractionError(Exception):
    """The source document has an unexpected shape."""


@dataclass(frozen=True)
class ValueSpec:
    ability: str
    object_path: str
    parameter: str
    value_name: str
    rank_count: int


DATA_VALUE_SPECS: tuple[ValueSpec, ...] = (
    ValueSpec("q", Q_PATH, "q.first_hit_base_damage", "Q1BaseDamage", 5),
    ValueSpec("q", Q_PATH, "q.recast_base_damage", "Q2BaseDamage", 5),
    ValueSpec("q", Q_PATH, "q.bonus_ad_ratio", "QCoeff", 5),
    ValueSpec("q", Q_PATH, "q.heal_percent_max_hp", "HealPercent", 5),
    ValueSpec("q", Q_PATH, "q.knockup_seconds", "KnockUpDuration", 1),
    ValueSpec("q", Q_PATH, "q.monster_damage_multiplier", "MonsterDamagePercent", 1),
    ValueSpec("w", W_PATH, "w.initial_base_damage", "InitialBaseDamage", 5),
    ValueSpec("w", W_PATH, "w.secondary_base_damage", "SecondaryBaseDamage", 5),
    ValueSpec("e", E_PATH, "e.base_damage", "Damage_Base", 5),
    ValueSpec("e", E_PATH, "e.percent_max_hp_magic", "PercentHPDamage", 5),
    ValueSpec("r", R_PATH, "r.base_damage", "EndDamage", 3),
    ValueSpec("r", R_PATH, "r.bonus_ad_ratio", "BonusADDamageRatio", 1),
    ValueSpec("r", R_PATH, "r.armor_penetration", "ArmorPen", 3),
    ValueSpec("r", R_PATH, "r.heal_fraction", "HealPercent", 1),
    ValueSpec("r", R_PATH, "r.damage_reduction", "DamageReduction", 1),
    ValueSpec("passive", PASSIVE_PATH, "passive.ad_per_stack_min", "PBonusADMin", 1),
    ValueSpec("passive", PASSIVE_PATH, "passive.ad_per_stack", "PBonusADMax", 1),
    ValueSpec("passive", PASSIVE_PATH, "passive.max_stacks", "MaxStacks", 1),
)

SPELL_FIELD_SPECS: tuple[tuple[str, str, str, str, int], ...] = (
    ("q", Q_PATH, "q.mana_cost", "mana", 5),
    ("w", W_PATH, "w.mana_cost", "mana", 5),
    ("e", E_PATH, "e.mana_cost", "mana", 5),
    ("r", R_PATH, "r.mana_cost", "mana", 3),
)

EFFECTIVE_COOLDOWN_SPECS: tuple[tuple[str, str, str, int], ...] = (
    ("q", Q_PATH, "q.cooldown_seconds", 5),
    ("w", W_PATH, "w.cooldown_seconds", 5),
    ("e", E_PATH, "e.cooldown_seconds", 5),
    ("r", R_PATH, "r.cooldown_seconds", 3),
)

LEGACY_COOLDOWN_SPECS: tuple[tuple[str, str, str, int], ...] = (
    ("q", Q_PATH, "q.cooldown_time_legacy", 5),
    ("w", W_PATH, "w.cooldown_time_legacy", 5),
    ("e", E_PATH, "e.cooldown_time_legacy", 5),
    ("r", R_PATH, "r.cooldown_time_legacy", 3),
)

CHAMPION_STAT_SPECS: tuple[tuple[str, str], ...] = (
    ("champion.base_attack_damage", "baseDamageModifiable"),
    ("champion.attack_damage_per_level", "damagePerLevelModifiable"),
    ("champion.base_hp", "baseHPModifiable"),
    ("champion.hp_per_level", "hpPerLevelModifiable"),
    ("champion.base_armor", "baseArmorModifiable"),
    ("champion.armor_per_level", "armorPerLevelModifiable"),
    ("champion.base_mr", "baseMR"),
    ("champion.mr_per_level", "mrPerLevel"),
    ("champion.base_move_speed", "baseMoveSpeedModifiable"),
    ("champion.attack_range", "attackRangeModifiable"),
    ("champion.attack_speed", "attackSpeedModifiable"),
)


@dataclass(frozen=True)
class Formula:
    name: str
    ability: str
    source_path: str
    parts: tuple[Mapping[str, Any], ...]
    supported: bool
    status: Status
    notes: str


def rank_slice(values: Any, rank_count: int, context: str) -> tuple[float, ...]:
    """Return ranks 1..N from a CDragon array where index 0 is unused."""
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ExtractionError(f"{context} must be a list")
    if len(values) < rank_count + 1:
        raise ExtractionError(
            f"{context} has {len(values)} entries, expected at least {rank_count + 1}"
        )
    selected = values[1 : rank_count + 1]
    numbers: list[float] = []
    for value in selected:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExtractionError(f"{context} contains a non-numeric value: {value!r}")
        numbers.append(float(value))
    return tuple(numbers)


def _object(document: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    node = document.get(path)
    if not isinstance(node, Mapping):
        raise ExtractionError(f"missing object {path}")
    spell = node.get("mSpell")
    if not isinstance(spell, Mapping):
        raise ExtractionError(f"missing {path}.mSpell")
    return spell


def _data_values(spell: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    entries = spell.get("DataValues")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ExtractionError(f"{path}.mSpell.DataValues must be a list")
    by_name: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            raise ExtractionError(f"{path}.mSpell.DataValues has a malformed entry")
        by_name[entry["name"]] = entry.get("values")
    return by_name


def extract_zaahen(
    document: Mapping[str, Any],
    *,
    url: str,
    content_version: str,
    sha256: str,
) -> list[Provenance]:
    """Extract the prototype's parameter subset with full provenance."""
    records: list[Provenance] = []

    for spec in DATA_VALUE_SPECS:
        spell = _object(document, spec.object_path)
        values = _data_values(spell, spec.object_path)
        if spec.value_name not in values:
            raise ExtractionError(f"{spec.object_path} has no DataValue {spec.value_name}")
        ranks = rank_slice(
            values[spec.value_name],
            spec.rank_count,
            f"{spec.object_path}.{spec.value_name}",
        )
        records.append(
            Provenance(
                champion=CHAMPION,
                ability=spec.ability,
                parameter=spec.parameter,
                ranks=ranks,
                source="communitydragon",
                url=url,
                source_version=content_version,
                source_path=(f"{spec.object_path}.mSpell.DataValues[{spec.value_name!r}].values"),
                source_sha256=sha256,
                extraction="DataValues array",
                transformation=f"index 1..{spec.rank_count} = ranks 1..{spec.rank_count}",
                status=Status.SOURCE_EXPLICIT,
                notes="Index 0 is unused; mapping confirmed by matching cooldowns.",
            )
        )

    for ability, object_path, parameter, field, rank_count in SPELL_FIELD_SPECS:
        spell = _object(document, object_path)
        ranks = rank_slice(spell.get(field), rank_count, f"{object_path}.mSpell.{field}")
        records.append(
            Provenance(
                champion=CHAMPION,
                ability=ability,
                parameter=parameter,
                ranks=ranks,
                source="communitydragon",
                url=url,
                source_version=content_version,
                source_path=f"{object_path}.mSpell.{field}",
                source_sha256=sha256,
                extraction="mSpell field array",
                transformation=f"index 1..{rank_count} = ranks 1..{rank_count}",
                status=Status.SOURCE_EXPLICIT,
            )
        )

    for ability, object_path, parameter, rank_count in EFFECTIVE_COOLDOWN_SPECS:
        spell = _object(document, object_path)
        cooldown = spell.get("Cooldown")
        if not isinstance(cooldown, Mapping):
            raise ExtractionError(f"{object_path}.mSpell.Cooldown must be an object")
        ranks = rank_slice(
            cooldown.get("values"),
            rank_count,
            f"{object_path}.mSpell.Cooldown.values",
        )
        records.append(
            Provenance(
                champion=CHAMPION,
                ability=ability,
                parameter=parameter,
                ranks=ranks,
                source="communitydragon",
                url=url,
                source_version=content_version,
                source_path=f"{object_path}.mSpell.Cooldown.values",
                source_sha256=sha256,
                extraction="SpellCooldown.values",
                transformation=f"index 1..{rank_count} = ranks 1..{rank_count}",
                status=Status.SOURCE_EXPLICIT,
                notes=(
                    "Effective cooldown. cooldownTime is a legacy mirror and must "
                    "not be used for this parameter."
                ),
            )
        )

    for ability, object_path, parameter, rank_count in LEGACY_COOLDOWN_SPECS:
        spell = _object(document, object_path)
        ranks = rank_slice(
            spell.get("cooldownTime"),
            rank_count,
            f"{object_path}.mSpell.cooldownTime",
        )
        records.append(
            Provenance(
                champion=CHAMPION,
                ability=ability,
                parameter=parameter,
                ranks=ranks,
                source="communitydragon",
                url=url,
                source_version=content_version,
                source_path=f"{object_path}.mSpell.cooldownTime",
                source_sha256=sha256,
                extraction="mSpell field array",
                transformation=f"index 1..{rank_count} = ranks 1..{rank_count}",
                status=Status.SOURCE_EXPLICIT,
                notes=(
                    "Legacy cooldownTime mirror, kept for diagnostics only; "
                    "not the effective cooldown."
                ),
            )
        )

    root = document.get(ROOT_PATH)
    if not isinstance(root, Mapping):
        raise ExtractionError(f"missing object {ROOT_PATH}")
    for parameter, field in CHAMPION_STAT_SPECS:
        entry = root.get(field)
        if not isinstance(entry, Mapping):
            raise ExtractionError(f"{ROOT_PATH}.{field} must be an object")
        value = entry.get("baseValue")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExtractionError(f"{ROOT_PATH}.{field}.baseValue must be numeric")
        records.append(
            Provenance(
                champion=CHAMPION,
                ability="champion",
                parameter=parameter,
                ranks=(float(value),),
                source="communitydragon",
                url=url,
                source_version=content_version,
                source_path=f"{ROOT_PATH}.{field}.baseValue",
                source_sha256=sha256,
                extraction="ModifiableFloat.baseValue",
                transformation="scalar",
                status=Status.SOURCE_EXPLICIT,
                notes="Champion stat block from CharacterRecords/Root.",
            )
        )

    return records


def extract_formula(
    document: Mapping[str, Any], object_path: str, calculation_name: str
) -> Formula:
    """Extract one mSpellCalculations entry without interpreting its semantics."""
    spell = _object(document, object_path)
    calculations = spell.get("mSpellCalculations")
    if not isinstance(calculations, Mapping):
        raise ExtractionError(f"{object_path}.mSpell.mSpellCalculations is not an object")
    calculation = calculations.get(calculation_name)
    if not isinstance(calculation, Mapping):
        raise ExtractionError(f"{object_path} has no calculation {calculation_name}")

    raw_parts = calculation.get("mFormulaParts")
    if raw_parts is None and calculation.get("__type") == "GameCalculationModified":
        multiplier = calculation.get("mMultiplier")
        raw_parts = [multiplier] if isinstance(multiplier, Mapping) else []
    if not isinstance(raw_parts, Sequence) or isinstance(raw_parts, (str, bytes)):
        raise ExtractionError(f"{calculation_name}.mFormulaParts must be a list")

    parts = tuple(raw_parts)
    part_types = {
        part.get("__type")
        for part in parts
        if isinstance(part, Mapping) and isinstance(part.get("__type"), str)
    }
    supported = bool(part_types) and part_types <= KNOWN_PART_TYPES
    status = Status.INFERRED if supported else Status.UNVERIFIED
    if supported and calculation.get("__type") == "GameCalculationModified":
        notes = (
            "Modified calculation: "
            f"references {calculation.get('mModifiedGameCalculation')!r} "
            "and multiplies it by a named value."
        )
    elif supported:
        notes = "Parts use known type names; semantics of mStat/mStatFormula are still inferred."
    else:
        notes = f"Unrecognised calculation part types: {sorted(part_types)}"
    return Formula(
        name=calculation_name,
        ability=object_path.split("/")[3],
        source_path=f"{object_path}.mSpell.mSpellCalculations[{calculation_name!r}]",
        parts=tuple(parts),
        supported=supported,
        status=status,
        notes=notes,
    )


def has_champion_stat_block(document: Mapping[str, Any]) -> bool:
    """Report whether the document exposes the champion stat block."""
    root = document.get(ROOT_PATH)
    return isinstance(root, Mapping) and isinstance(root.get("damagePerLevelModifiable"), Mapping)


def formula_status(formula: Formula, dependencies: Sequence[Status]) -> Status:
    """Combine the formula's own status with the status of its operands."""
    return combine_statuses(formula.status, *dependencies)
