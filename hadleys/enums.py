"""String enums preserve the existing JSON and MQTT wire values."""

from enum import StrEnum


class TransportKind(StrEnum):
    FREIGHT = "freight"
    GARBAGE = "garbage"
    PLUMBER = "plumber"
    REPAIR = "repair"
    SLUDGE = "sludge"
    TRANSIT = "transit"


class TransportState(StrEnum):
    DRIVING = "DRIVING"
    PARKED = "PARKED"
    CIRCULATING = "CIRCULATING"
    DELIVER = "DELIVER"
    IDLE = "IDLE"
    LOADING = "LOADING"
    PUMPING = "PUMPING"
    REPAIRING = "REPAIRING"
    RETURN = "RETURN"
    TO_BIN = "TO_BIN"
    TO_DEPOT = "TO_DEPOT"
    TO_GARAGE = "TO_GARAGE"
    TO_HOUSE = "TO_HOUSE"
    TO_STATION = "TO_STATION"
    TO_STORE = "TO_STORE"
    TO_TARGET = "TO_TARGET"
    UNLOADING = "UNLOADING"
    WAITING = "WAITING"
    WAIT_GATE = "WAIT_GATE"
