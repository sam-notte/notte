from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.sdk.endoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    ListRequestDict,
    SessionDebugResponse,
    SessionListRequest,
    SessionRequest,
    SessionResponse,
    SessionStartRequestDict,
    TabSessionDebugRequest,
    TabSessionDebugResponse,
)


@final
class SessionsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    SESSION_START = "start"
    SESSION_CLOSE = "{session_id}/close"
    SESSION_STATUS = "{session_id}"
    SESSION_LIST = ""
    SESSION_DEBUG = "debug/{session_id}"
    SESSION_DEBUG_TAB = "debug/{session_id}/tab"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initializes a SessionsClient for managing Notte API sessions.
        
        Args:
            api_key: Optional API key used for authentication.
            server_url: Optional URL of the Notte API server.
        """
        super().__init__(base_endpoint_path="sessions", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        """
        Returns the endpoint for initiating a session.
        
        Constructs a NotteEndpoint with the session start path, HTTP POST method, and
        SessionResponse as the expected response type.
        """
        return NotteEndpoint(path=SessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def session_close_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs an endpoint for closing a session via a DELETE request.
        
        If a session ID is provided, it is formatted into the endpoint path.
        Returns a NotteEndpoint configured with the DELETE method and expecting a SessionResponse.
        
        Args:
            session_id: Optional session identifier to embed in the endpoint URL.
        """
        path = SessionsClient.SESSION_CLOSE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="DELETE")

    @staticmethod
    def session_status_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Returns an endpoint to query a session's status.
        
        If a session_id is provided, it is inserted into the endpoint path to target a specific session.
        
        Args:
            session_id: Optional session identifier to include in the request path.
        
        Returns:
            NotteEndpoint[SessionResponse]: An endpoint configured for a GET request that returns a SessionResponse.
        """
        path = SessionsClient.SESSION_STATUS
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="GET")

    @staticmethod
    def session_list_endpoint(params: SessionListRequest | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Creates a NotteEndpoint for listing sessions.
        
        This function returns a NotteEndpoint configured to perform a GET request using the
        session list path defined in SessionsClient. Optional query parameters can be provided
        via the params argument to tailor the session listing response.
        
        Args:
            params: An optional SessionListRequest object containing query parameters.
            
        Returns:
            A NotteEndpoint preconfigured for listing sessions with a SessionResponse payload.
        """
        return NotteEndpoint(
            path=SessionsClient.SESSION_LIST,
            response=SessionResponse,
            method="GET",
            request=None,
            params=params,
        )

    @staticmethod
    def session_debug_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionDebugResponse]:
        """
        Constructs a session debug endpoint.
        
        If a session identifier is provided, the endpoint path is formatted to include it.
        
        Args:
            session_id: An optional session identifier to incorporate in the debug endpoint path.
        
        Returns:
            A NotteEndpoint configured for a GET request that expects a SessionDebugResponse.
        """
        path = SessionsClient.SESSION_DEBUG
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionDebugResponse, method="GET")

    @staticmethod
    def session_debug_tab_endpoint(
        session_id: str | None = None, params: TabSessionDebugRequest | None = None
    ) -> NotteEndpoint[TabSessionDebugResponse]:
        """
        Constructs a NotteEndpoint for retrieving debug information for a specific session tab.
        
        If a session identifier is provided, the endpoint path is formatted accordingly.
        Optional tab-specific debug parameters can be supplied via the params argument.
        Returns a NotteEndpoint configured with a GET method for a TabSessionDebugResponse.
        """
        path = SessionsClient.SESSION_DEBUG_TAB
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(
            path=path,
            response=TabSessionDebugResponse,
            method="GET",
            params=params,
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns a sequence of endpoints for session management API operations.
        
        This function aggregates all Notte endpoints related to sessions, including starting, closing,
        status checking, listing, and debugging sessions. Each endpoint is constructed using the corresponding
        static method of the SessionsClient.
        """
        return [
            SessionsClient.session_start_endpoint(),
            SessionsClient.session_close_endpoint(),
            SessionsClient.session_status_endpoint(),
            SessionsClient.session_list_endpoint(),
            SessionsClient.session_debug_endpoint(),
            SessionsClient.session_debug_tab_endpoint(),
        ]

    @property
    def session_id(self) -> str | None:
        """
        Retrieves the session ID from the last session response.
        
        Returns:
            The session ID if a previous session response exists; otherwise, None.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieve the session ID for the current session.
        
        If a session_id is provided, it is returned directly. Otherwise, the method retrieves
        the session ID from the most recent session response. If no session ID is available,
        a ValueError is raised.
          
        Args:
            session_id: An optional session identifier to use.
        
        Returns:
            The session ID as a string.
        
        Raises:
            ValueError: If no session ID is provided and no session exists.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise ValueError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def start(self, **data: Unpack[SessionStartRequestDict]) -> SessionResponse:
        """
        Start a new session via the Notte API.
        
        Validates the provided session start data, sends it to the session start endpoint,
        updates the latest session response, and returns the session response.
        
        Keyword Arguments:
            **data: Arbitrary keyword arguments that form the session start request data as defined by SessionStartRequestDict.
        
        Returns:
            SessionResponse: The response generated from initiating the session.
        """
        request = SessionRequest.model_validate(data)
        response = self.request(SessionsClient.session_start_endpoint().with_request(request))
        self._last_session_response = response
        return response

    def close(self, session_id: str | None = None) -> SessionResponse:
        """
        Closes the active session.
        
        Retrieves the session ID from the provided argument or the client's last session response,
        sends a request to the API to close the session, validates the response, and clears the stored
        session data.
        
        Args:
            session_id: Optional session identifier to close. If not provided, the stored session ID is used.
        
        Returns:
            SessionResponse: The validated response from the session close operation.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_close_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = None
        return response

    def status(self, session_id: str | None = None) -> SessionResponse:
        """
        Retrieve the status of a session from the Notte API.
        
        If a session ID is provided, it is used to query the session status; otherwise, the method falls
        back to the last active session ID retrieved via get_session_id. The endpoint is constructed
        dynamically based on the session ID, and the response is validated and cached before being returned.
        
        Args:
            session_id: Optional session identifier; if omitted, the last recorded session ID is used.
        
        Returns:
            SessionResponse: The validated status of the session.
        
        Raises:
            ValueError: If no valid session ID is available.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_status_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[SessionResponse]:
        """
        List sessions with optional filtering parameters.
        
        Validates the provided keyword arguments using SessionListRequest, constructs the
        list endpoint, and returns a sequence of session responses based on the filters.
        
        Keyword Args:
            **data: Optional filtering criteria as defined in ListRequestDict.
        
        Returns:
            A sequence of SessionResponse objects.
        """
        params = SessionListRequest.model_validate(data)
        endpoint = SessionsClient.session_list_endpoint(params=params)
        return self.request_list(endpoint)

    def debug_info(self, session_id: str | None = None) -> SessionDebugResponse:
        """
        Retrieves debug information for a session.
        
        If a session ID is provided, that session's debug info is retrieved; otherwise the current active session is used.
        Constructs the debug endpoint and performs the request to obtain session debugging details.
        
        Args:
            session_id: Optional session identifier. If omitted, the last active session ID is used.
        
        Returns:
            SessionDebugResponse: The debug response for the session.
        
        Raises:
            ValueError: If no valid session ID is available.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_debug_endpoint(session_id=session_id)
        return self.request(endpoint)

    def debug_tab_info(self, session_id: str | None = None, tab_idx: int | None = None) -> TabSessionDebugResponse:
        """
        Retrieve debug information for a specific tab in a session.
        
        If no session ID is provided, the method obtains it from the current session context.
        When a tab index is specified, the debug request targets that particular tab.
        
        Args:
            session_id: Optional session identifier. If omitted, the last active session is used.
            tab_idx: Optional index of the tab for which to retrieve debug information.
        
        Returns:
            TabSessionDebugResponse: The debug response for the specified session tab.
        
        Raises:
            ValueError: If no valid session ID is available.
        """
        session_id = self.get_session_id(session_id)
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = SessionsClient.session_debug_tab_endpoint(session_id=session_id, params=params)
        return self.request(endpoint)
