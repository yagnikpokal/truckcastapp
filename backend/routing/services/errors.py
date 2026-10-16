"""Errors that are safe to show to the driver."""


class UserError(Exception):
    """The trip request itself cannot be planned."""


class UpstreamError(Exception):
    """A routing, geocoding, or weather service failed."""
