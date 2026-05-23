"""Driver assistant conversation states."""


class StatesGroupMeta(type):
    pass


class StatesGroup(metaclass=StatesGroupMeta):
    pass


class State:
    def __init__(self, name: str = ""):
        self.name = name

    def __str__(self) -> str:
        return self.name or id(self)


class DriverStates(StatesGroup):
    """Driver assistant states."""

    WAIT_VEHICLE_TITLE = State("WAIT_DRIVER_VEHICLE_TITLE")
    WAIT_VEHICLE_MILEAGE = State("WAIT_DRIVER_VEHICLE_MILEAGE")
    WAIT_VEHICLE_SERVICE_KM = State("WAIT_DRIVER_VEHICLE_SERVICE_KM")
    WAIT_VEHICLE_SERVICE_MONTHS = State("WAIT_DRIVER_VEHICLE_SERVICE_MONTHS")
    WAIT_FUEL_MILEAGE = State("WAIT_DRIVER_FUEL_MILEAGE")
    WAIT_FUEL_LITERS = State("WAIT_DRIVER_FUEL_LITERS")
    WAIT_FUEL_COST = State("WAIT_DRIVER_FUEL_COST")
    WAIT_FUEL_FULL = State("WAIT_DRIVER_FUEL_FULL")
    WAIT_FUEL_STATION = State("WAIT_DRIVER_FUEL_STATION")
    WAIT_SERVICE_MILEAGE = State("WAIT_DRIVER_SERVICE_MILEAGE")
