"""Curated vehicle presets used by the driver assistant."""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class VehiclePreset:
    """A lightweight vehicle specification preset."""

    slug: str
    label: str
    title: str
    make: str
    model: str
    year: Optional[int]
    generation: Optional[str]
    body_type: str
    engine_volume_l: float
    engine_power_hp: Optional[int]
    fuel_type: str
    transmission: str
    drive_type: str
    consumption_city_l_per_100: Optional[float]
    consumption_highway_l_per_100: Optional[float]
    consumption_mixed_l_per_100: Optional[float]
    service_interval_km: int
    service_interval_months: int
    confidence: str
    note: str

    def as_dict(self) -> dict:
        """Return a JSON/API friendly representation."""
        return asdict(self)

    def vehicle_kwargs(self) -> dict:
        """Return fields that can be saved on a DriverVehicle snapshot."""
        return {
            "preset_slug": self.slug,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "body_type": self.body_type,
            "engine_volume_l": self.engine_volume_l,
            "engine_power_hp": self.engine_power_hp,
            "fuel_type": self.fuel_type,
            "transmission": self.transmission,
            "drive_type": self.drive_type,
            "expected_consumption_city_l_per_100": self.consumption_city_l_per_100,
            "expected_consumption_highway_l_per_100": self.consumption_highway_l_per_100,
            "expected_consumption_mixed_l_per_100": self.consumption_mixed_l_per_100,
            "vehicle_specs_note": self.note,
        }


VEHICLE_PRESETS: tuple[VehiclePreset, ...] = (
    VehiclePreset(
        slug="hyundai_verna_2007_1_4_mt",
        label="Hyundai Verna 2007 1.4 MT",
        title="Hyundai Verna 2007",
        make="Hyundai",
        model="Verna",
        year=2007,
        generation="MC",
        body_type="седан",
        engine_volume_l=1.4,
        engine_power_hp=97,
        fuel_type="petrol",
        transmission="manual",
        drive_type="fwd",
        consumption_city_l_per_100=8.0,
        consumption_highway_l_per_100=5.1,
        consumption_mixed_l_per_100=7.1,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентировочный расход для 1.4 бензин МКПП; реальный зависит от состояния авто и режима езды.",
    ),
    VehiclePreset(
        slug="lada_niva_21213_1997_1_7_mt",
        label="Нива 21213 1997 1.7 MT",
        title="Нива 21213 1997",
        make="Lada",
        model="Нива 21213",
        year=1997,
        generation="21213",
        body_type="3-дверный внедорожник",
        engine_volume_l=1.7,
        engine_power_hp=79,
        fuel_type="petrol",
        transmission="manual",
        drive_type="awd",
        consumption_city_l_per_100=13.0,
        consumption_highway_l_per_100=8.5,
        consumption_mixed_l_per_100=10.8,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="low",
        note="Ориентир для карбюраторной Нивы 21213; у старых авто разброс расхода часто высокий.",
    ),
    VehiclePreset(
        slug="lada_niva_21214_1_7_mt",
        label="Нива 21214 1.7 MT инжектор",
        title="Нива 21214",
        make="Lada",
        model="Нива 21214",
        year=None,
        generation="21214",
        body_type="3-дверный внедорожник",
        engine_volume_l=1.7,
        engine_power_hp=83,
        fuel_type="petrol",
        transmission="manual",
        drive_type="awd",
        consumption_city_l_per_100=12.0,
        consumption_highway_l_per_100=8.3,
        consumption_mixed_l_per_100=10.0,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="low",
        note="Ориентир для инжекторной Нивы 21214; фактический расход лучше уточнять по журналу заправок.",
    ),
    VehiclePreset(
        slug="ford_focus_2_hatchback_1_6_100_mt",
        label="Ford Focus II хетчбек 1.6 100 MT",
        title="Ford Focus II хетчбек",
        make="Ford",
        model="Focus II",
        year=None,
        generation="II",
        body_type="хетчбек",
        engine_volume_l=1.6,
        engine_power_hp=100,
        fuel_type="petrol",
        transmission="manual",
        drive_type="fwd",
        consumption_city_l_per_100=8.7,
        consumption_highway_l_per_100=5.5,
        consumption_mixed_l_per_100=6.7,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентир для Focus II 1.6 100 л.с. МКПП.",
    ),
    VehiclePreset(
        slug="ford_focus_2_hatchback_1_6_115_mt",
        label="Ford Focus II хетчбек 1.6 115 MT",
        title="Ford Focus II хетчбек",
        make="Ford",
        model="Focus II",
        year=None,
        generation="II",
        body_type="хетчбек",
        engine_volume_l=1.6,
        engine_power_hp=115,
        fuel_type="petrol",
        transmission="manual",
        drive_type="fwd",
        consumption_city_l_per_100=8.7,
        consumption_highway_l_per_100=5.1,
        consumption_mixed_l_per_100=6.4,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентир для Focus II 1.6 Ti-VCT 115 л.с. МКПП.",
    ),
    VehiclePreset(
        slug="mitsubishi_pajero_pinin_1_8_mt_awd",
        label="Mitsubishi Pajero Pinin 1.8 MT 4x4",
        title="Mitsubishi Pajero Pinin",
        make="Mitsubishi",
        model="Pajero Pinin",
        year=None,
        generation="H60",
        body_type="внедорожник",
        engine_volume_l=1.8,
        engine_power_hp=114,
        fuel_type="petrol",
        transmission="manual",
        drive_type="awd",
        consumption_city_l_per_100=11.8,
        consumption_highway_l_per_100=7.8,
        consumption_mixed_l_per_100=9.3,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентир для Pajero Pinin 1.8 бензин МКПП 4x4.",
    ),
    VehiclePreset(
        slug="mitsubishi_pajero_pinin_2_0_mt_awd",
        label="Mitsubishi Pajero Pinin 2.0 MT 4x4",
        title="Mitsubishi Pajero Pinin",
        make="Mitsubishi",
        model="Pajero Pinin",
        year=None,
        generation="H60",
        body_type="внедорожник",
        engine_volume_l=2.0,
        engine_power_hp=129,
        fuel_type="petrol",
        transmission="manual",
        drive_type="awd",
        consumption_city_l_per_100=12.2,
        consumption_highway_l_per_100=8.0,
        consumption_mixed_l_per_100=9.5,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентир для Pajero Pinin 2.0 бензин МКПП 4x4.",
    ),
    VehiclePreset(
        slug="lada_kalina_1118_2008_1_6_8v_mt",
        label="Lada Kalina 1118 2008 1.6 8V MT",
        title="Lada Kalina 1118 2008",
        make="Lada",
        model="Kalina 1118",
        year=2008,
        generation="I",
        body_type="седан",
        engine_volume_l=1.6,
        engine_power_hp=81,
        fuel_type="petrol",
        transmission="manual",
        drive_type="fwd",
        consumption_city_l_per_100=9.0,
        consumption_highway_l_per_100=5.8,
        consumption_mixed_l_per_100=7.1,
        service_interval_km=10000,
        service_interval_months=12,
        confidence="medium",
        note="Ориентир для Kalina I седан 1.6 8V МКПП.",
    ),
)

_PRESET_BY_SLUG = {preset.slug: preset for preset in VEHICLE_PRESETS}


def list_vehicle_presets() -> tuple[VehiclePreset, ...]:
    """Return all curated vehicle presets."""
    return VEHICLE_PRESETS


def get_vehicle_preset(slug: str) -> Optional[VehiclePreset]:
    """Return one vehicle preset by slug."""
    return _PRESET_BY_SLUG.get(slug)

