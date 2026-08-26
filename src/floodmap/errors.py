# Copyright (c) 2026 Martial Systems LLC. All rights reserved.


class GateError(RuntimeError):
    """Stage hard gate failed."""


class CrsMissingError(GateError):
    """Layer has no CRS; refuse rather than assume."""


class CrsMismatchError(GateError):
    """CRS is present but is not the locked EPSG."""


class EmptyHucError(GateError):
    """HUC polygon missing or empty."""


class FreezeError(GateError):
    """Imported occupancy freeze does not match locked numbers."""


class ClaimBanError(GateError):
    """Report text hit a banned claim."""
