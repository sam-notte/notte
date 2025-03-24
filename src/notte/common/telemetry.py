import importlib.metadata as metadata
import logging
import os
import platform
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger("notte.telemetry")

try:
    # Try to get the version of the package
    __version__ = metadata.version("notte")
except Exception:
    __version__ = "unknown"


TELEMETRY_ENABLED: bool = os.environ.get("ANONYMIZED_TELEMETRY", "true").lower() != "false"

# anonymous ID
INSTALLATION_ID: str = str(uuid.uuid4())


POSTHOG_API_KEY: str = os.environ.get("POSTHOG_API_KEY", "phc_your_default_key_here")

# PostHog host URL
POSTHOG_HOST: str = os.environ.get("POSTHOG_HOST", "https://app.posthog.com")


F = TypeVar("F", bound=Callable[..., Any])

# avoid unbound variable errors
posthog = None
posthog_available = False

try:
    import posthog

    posthog_available = True
except (ImportError, ModuleNotFoundError):
    posthog = None  # Explicitly set to None
    logger.debug("PostHog not installed. Telemetry will be disabled.")
    posthog_available = False


def setup_posthog() -> Any | None:
    """Initialize a PostHog client for telemetry.
    
    Attempts to create and return a PostHog client using the configured API key and host if telemetry
    is enabled and the PostHog module is available. Returns None if telemetry is disabled, the client is
    unavailable, or initialization fails.
    """
    if not TELEMETRY_ENABLED or not posthog_available or posthog is None:
        return None

    try:
        # Use explicit Any type for client to resolve unknown type warnings
        # And ignore the unknown type for posthog.Posthog
        client: Any = posthog.Posthog(
            api_key=POSTHOG_API_KEY,
            host=POSTHOG_HOST,
        )
        return client
    except Exception as e:
        logger.debug(f"Failed to initialize PostHog: {e}")
        return None


# Initialize PostHog
posthog_client = setup_posthog()


def get_system_info() -> dict[str, Any]:
    """Return anonymous system information.
    
    Returns:
        dict[str, Any]: A dictionary with the following keys:
            os: The name of the operating system.
            python_version: The current Python version.
            notte_version: The installed Notte package version or "unknown" if not available.
    """
    return {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "notte_version": __version__,
    }


def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """
    Capture a telemetry event with system details.
    
    If telemetry is enabled and a PostHog client is available, this function sends an event
    identified by the given name to the telemetry service. Any provided properties are merged
    with anonymous system information (such as operating system and software versions) before
    sending. If telemetry is disabled or the client is unavailable, the function exits without
    sending an event. Any exceptions during event capture are logged at the debug level.
    
    Args:
        event_name: The identifier for the event.
        properties: Optional dictionary of additional event attributes.
    """
    if not TELEMETRY_ENABLED or posthog_client is None:
        return

    try:
        event_properties = properties or {}

        # Add system info
        event_properties.update(get_system_info())

        # Send event to PostHog
        posthog_client.capture(distinct_id=INSTALLATION_ID, event=event_name, properties=event_properties)
    except Exception as e:
        logger.debug(f"Telemetry error: {e}")


def track_usage(method_name: str | None = None) -> Callable[[F], F]:
    """Decorator to track function usage with telemetry.
    
    This decorator captures a telemetry event before executing the decorated function.
    It sends an event named "method.called.<name>" where <name> is either the provided
    custom method name or, if omitted, the function's module and name.
    
    Args:
        method_name: Optional; a custom identifier for the method. If not provided, the event
                     name is derived from the function's module and name.
    
    Returns:
        A decorator that wraps the target function, recording its invocation via a telemetry event.
    """

    def decorator(func: F) -> F:
        """
        Decorator for tracking function usage via telemetry events.
        
        Wraps the provided function to capture a telemetry event before its execution.
        If a custom method name is available from the enclosing scope, it is used; otherwise,
        the event name defaults to the function's module and name. After recording the event,
        the original function is executed and its result is returned.
        """
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Capture event before function execution
            event_name = method_name if method_name is not None else f"{func.__module__}.{func.__name__}"
            capture_event(f"method.called.{event_name}")

            # Execute the function
            result = func(*args, **kwargs)

            # Return the original result
            return result

        return wrapper  # type: ignore

    return decorator
