from decimal import Decimal, InvalidOperation

from pint import DimensionalityError, UndefinedUnitError, UnitRegistry

registry = UnitRegistry(non_int_type=Decimal)

EXPECTED_UNITS = {
    "force": "N",
    "pressure": "Pa",
    "temperature": "K",
    "torque": "N*m",
    "voltage": "V",
    "current": "A",
    "length": "m",
    "mass": "kg",
}

PROPERTY_ALIASES = {
    "force": {"force", "kraft", "kraftmessung", "kraftsensor", "wägezelle", "waegezelle", "load cell"},
    "pressure": {"pressure", "druck", "drucksensor"},
    "temperature": {"temperature", "temperatur", "temperatursensor"},
    "torque": {"torque", "drehmoment"},
    "voltage": {"voltage", "spannung"},
    "current": {"current", "strom", "stromstärke"},
    "length": {"length", "länge", "weg", "abstand"},
    "mass": {"mass", "masse", "gewicht"},
}


def normalize_property(name):
    value = (name or "").strip().casefold()
    return next((key for key, aliases in PROPERTY_ALIASES.items() if value in aliases), value)


def unit_matches_property(property_name, unit):
    expected = EXPECTED_UNITS.get(normalize_property(property_name))
    if not expected:
        return True
    try:
        return registry.parse_units(unit).dimensionality == registry.parse_units(expected).dimensionality
    except (ValueError, TypeError, UndefinedUnitError):
        return False


def comparable_range(min_value, max_value, unit, target_value, target_unit):
    """Vergleicht nur physikalisch kompatible Einheiten; kg wird nicht als N interpretiert."""
    try:
        target = registry.Quantity(Decimal(str(target_value)), target_unit).to_base_units()
        lower = (
            registry.Quantity(Decimal(str(min_value)), unit).to_base_units()
            if min_value is not None
            else None
        )
        upper = (
            registry.Quantity(Decimal(str(max_value)), unit).to_base_units()
            if max_value is not None
            else None
        )
        if lower is not None and lower.dimensionality != target.dimensionality:
            return None
        if upper is not None and upper.dimensionality != target.dimensionality:
            return None
        if lower is None and upper is None:
            return None
        fits = (lower is None or lower.magnitude <= target.magnitude) and (
            upper is None or target.magnitude <= upper.magnitude
        )
        margin = (
            float((upper.magnitude - target.magnitude) / abs(target.magnitude))
            if upper and target.magnitude
            else None
        )
        return {
            "fits": fits,
            "at_limit": upper is not None and upper.magnitude == target.magnitude,
            "margin": margin,
        }
    except (ValueError, TypeError, InvalidOperation, UndefinedUnitError, DimensionalityError):
        return None
