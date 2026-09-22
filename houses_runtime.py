"""Compatibility CLI for the house controller process."""

from hadleys.controllers.runtime import Runtime, main
from hadleys.controllers.programs import (
    PROGRAMS,
    thermostat,
    prog_comfort,
    prog_eco,
    prog_night_setback,
    prog_storm_ready,
    prog_dumb,
)

if __name__ == "__main__":
    main()
