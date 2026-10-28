class ConfigurationError(RuntimeError):
    """The application requires a configuration change."""


class BackendError(RuntimeError):
    """A dependency failed or returned an unusable response."""
