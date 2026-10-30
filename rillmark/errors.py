"""Narrow exception types. Raise where the fact is known; catch only where you can act."""


class RillmarkError(Exception):
    """Base class for all expected, reportable failures."""


class ConfigError(RillmarkError):
    """Missing or invalid configuration (env, config/selection.json)."""


class SelectionError(RillmarkError):
    """Selection below the minimum, or the required YouTube article is missing."""


class FetchError(RillmarkError):
    """Zendesk fetch failed or pagination was incomplete."""


class ConversionError(RillmarkError):
    """An article could not be converted, or its file exceeds the token budget."""


class StoreResolutionError(RillmarkError):
    """The marked vector store is missing, ambiguous, or fails marker validation."""


class RemoteStateError(RillmarkError):
    """Listing the store's attachments failed or was incomplete."""


class UploadError(RillmarkError):
    """Upload, attach, or completion polling failed for one file."""


class PublishError(RillmarkError):
    """The run artifact could not be published."""
