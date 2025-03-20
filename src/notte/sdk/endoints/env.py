from collections.abc import Sequence
from typing import TypeVar, Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.controller.space import SpaceCategory
from notte.data.space import DataSpace
from notte.errors.sdk import InvalidRequestError
from notte.sdk.endoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequest,
    ScrapeRequestDict,
    SessionRequestDict,
    SessionResponse,
    StepRequest,
    StepRequestDict,
)

TSessionRequestDict = TypeVar("TSessionRequestDict", bound=SessionRequestDict)


@final
class EnvClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    ENV_SCRAPE = "scrape"
    ENV_OBSERVE = "observe"
    ENV_STEP = "step"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initialize an EnvClient for Notte API environment interactions.
        
        Optionally configures the client with an API key and server URL, sets the base endpoint
        path to "env", and initializes the last session response to None.
        """
        super().__init__(base_endpoint_path="env", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def env_scrape_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Return a NotteEndpoint configured for the scrape action.
        
        Constructs and returns a NotteEndpoint instance for sending scrape requests to the
        Notte API. The endpoint uses the path defined by EnvClient.ENV_SCRAPE, expects an
        ObserveResponse, and employs the POST method.
        """
        return NotteEndpoint(path=EnvClient.ENV_SCRAPE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_observe_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for the observe action.
        
        Returns a NotteEndpoint preconfigured to send POST requests to the observe endpoint (EnvClient.ENV_OBSERVE) and expect an ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_OBSERVE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_step_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Returns a NotteEndpoint configured for the step action.
        
        This endpoint is set up to perform a POST request to the step endpoint of the Notte API and
        expects an ObserveResponse as the response type.
        """
        return NotteEndpoint(path=EnvClient.ENV_STEP, response=ObserveResponse, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns the endpoints for environmental actions.
        
        Aggregates the scrape, observe, and step endpoints from EnvClient to handle corresponding
        Notte API requests.
        """
        return [
            EnvClient.env_scrape_endpoint(),
            EnvClient.env_observe_endpoint(),
            EnvClient.env_step_endpoint(),
        ]

    @property
    def session_id(self) -> str | None:
        """
        Returns the session identifier from the last session response, or None if unavailable.
        
        This property retrieves the session identifier that was stored from the most recent session response.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieves the session ID for the current session.
        
        If a session ID is provided, it is returned directly. Otherwise, the session ID is obtained from
        the last session response. Raises ValueError if no session information is available.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise ValueError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> Observation:
        """
        Sends a scrape request and returns a formatted observation.
        
        Validates the provided scrape request data against the ScrapeRequest model and ensures that either a URL or a session ID is supplied. Sends the request to the scrape endpoint and processes the response into an Observation.
        
        Args:
            data: Arbitrary keyword arguments matching ScrapeRequestDict. Must include either 'url' or 'session_id'.
        
        Returns:
            Observation: The observation constructed from the scrape response.
        
        Raises:
            InvalidRequestError: If both 'url' and 'session_id' are missing.
        """
        request = ScrapeRequest.model_validate(data)
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        endpoint = EnvClient.env_scrape_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def observe(self, **data: Unpack[ObserveRequestDict]) -> Observation:
        """
        Sends an observation request and returns the formatted observation.
        
        Validates the input data using the ObserveRequest model. One of 'url' or
        'session_id' must be provided, otherwise an InvalidRequestError is raised.
        The method sends the validated request to the observe endpoint and processes
        the API response into an Observation.
         
        Args:
            data: Keyword arguments for constructing an ObserveRequest.
         
        Raises:
            InvalidRequestError: If neither 'url' nor 'session_id' is provided.
         
        Returns:
            Observation: The observation data derived from the API response.
        """
        request = ObserveRequest.model_validate(data)
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        endpoint = EnvClient.env_observe_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def step(self, **data: Unpack[StepRequestDict]) -> Observation:
        """
        Processes a step request and returns the resulting observation.
        
        Validates keyword arguments against the StepRequest model, sends the request to the
        step endpoint, and converts the API response into an Observation object.
        
        Args:
            **data: Arbitrary keyword arguments representing the payload for the step request.
        
        Returns:
            An Observation object constructed from the API response.
        """
        request = StepRequest.model_validate(data)
        endpoint = EnvClient.env_step_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def _format_observe_response(self, response: ObserveResponse) -> Observation:
        """
        Formats an observe response into an Observation object.
        
        Updates the client's last session response with the provided session and builds
        an Observation that includes metadata, screenshot, and, if available, the action and
        data spaces from the response.
        
        Args:
            response: An ObserveResponse containing session, metadata, screenshot, and optional
                      action and data space details.
        
        Returns:
            An Observation instance constructed from the response.
        """
        self._last_session_response = response.session
        return Observation(
            metadata=response.metadata,
            screenshot=response.screenshot,
            space=(
                None
                if response.space is None
                else ActionSpace(
                    description=response.space.description,
                    raw_actions=response.space.actions,
                    category=None if response.space.category is None else SpaceCategory(response.space.category),
                    _embeddings=None,
                )
            ),
            data=(
                None
                if response.data is None
                else DataSpace(
                    markdown=response.data.markdown,
                    images=(None if response.data.images is None else response.data.images),
                    structured=None if response.data.structured is None else response.data.structured,
                )
            ),
        )
