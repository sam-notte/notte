from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.agents.falco.types import StepAgentOutput
from notte.sdk.endoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    AgentListRequest,
    AgentResponse,
    AgentRunRequest,
    AgentRunRequestDict,
    ListRequestDict,
)
from notte.sdk.types import (
    AgentStatusResponse as _AgentStatusResponse,
)

AgentStatusResponse = _AgentStatusResponse[StepAgentOutput]


@final
class AgentsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    AGENT_RUN = "run"
    AGENT_STOP = "{agent_id}/stop"
    AGENT_STATUS = "{agent_id}"
    AGENT_LIST = ""

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initializes an AgentsClient instance for agent management.
        
        Initializes the base client with the 'agents' endpoint, optionally using a provided API key
        and server URL for authentication and connection. Also sets up an internal tracker for the
        last agent response.
            
        Args:
            api_key: Optional API key for authenticating requests.
            server_url: Optional URL of the server to connect to.
        """
        super().__init__(base_endpoint_path="agents", api_key=api_key, server_url=server_url)
        self._last_agent_response: AgentResponse | None = None

    @staticmethod
    def agent_run_endpoint() -> NotteEndpoint[AgentResponse]:
        """
        Creates a NotteEndpoint for running an agent.
        
        Returns a NotteEndpoint configured with the agent run endpoint path, the POST method, and the
        expected AgentResponse type.
        """
        return NotteEndpoint(path=AgentsClient.AGENT_RUN, response=AgentResponse, method="POST")

    @staticmethod
    def agent_stop_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Constructs a NotteEndpoint for stopping an agent.
        
        If an agent ID is provided, the endpoint path is formatted with that ID.
        The returned endpoint is configured to use the DELETE method and expects an
        AgentStatusResponse.
            
        Args:
            agent_id: Optional identifier of the agent to stop; if omitted, the default
                      endpoint path is used.
        """
        path = AgentsClient.AGENT_STOP
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentStatusResponse]:
        """
        Creates a NotteEndpoint for retrieving an agent's status.
        
        If an agent ID is provided, it formats the endpoint URL with the given value.
        The returned endpoint is configured to execute a GET request and expects an AgentStatusResponse.
        
        Args:
            agent_id: An optional identifier to include in the endpoint URL.
            
        Returns:
            A NotteEndpoint configured for fetching an agent's status.
        """
        path = AgentsClient.AGENT_STATUS
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="GET")

    @staticmethod
    def agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Creates an HTTP GET endpoint for listing agents.
        
        Args:
            params (AgentListRequest, optional): Optional query parameters to filter the agent list.
        
        Returns:
            NotteEndpoint[AgentResponse]: A configured endpoint for retrieving agent data.
        """
        return NotteEndpoint(
            path=AgentsClient.AGENT_LIST,
            response=AgentResponse,
            method="GET",
            request=None,
            params=params,
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns a sequence of endpoints for agent operations.
        
        The returned list includes endpoints for running, stopping, checking status,
        and listing agents.
        """
        return [
            AgentsClient.agent_run_endpoint(),
            AgentsClient.agent_stop_endpoint(),
            AgentsClient.agent_status_endpoint(),
            AgentsClient.agent_list_endpoint(),
        ]

    @property
    def agent_id(self) -> str | None:
        """
        Returns the agent ID from the last agent response if available; otherwise, returns None.
        """
        return self._last_agent_response.agent_id if self._last_agent_response is not None else None

    def get_agent_id(self, agent_id: str | None = None) -> str:
        """
        Retrieve the agent identifier.
        
        If an agent ID is provided, it is returned immediately. Otherwise, the method extracts
        the agent ID from the last recorded agent response. A ValueError is raised if neither is available.
        
        Args:
            agent_id: Optional; a specific agent identifier. If not provided, the identifier is
                      obtained from the last agent response.
        
        Returns:
            The resolved agent identifier.
        
        Raises:
            ValueError: If no agent identifier is available.
        """
        if agent_id is None:
            if self._last_agent_response is None:
                raise ValueError("No agent to get agent id from")
            agent_id = self._last_agent_response.agent_id
        return agent_id

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """
        Runs an agent with the specified configuration.
        
        Validates the provided keyword arguments against the AgentRunRequest model, sends a request
        to the agent run endpoint, updates the client's last agent response, and returns the resulting
        AgentResponse.
        
        Args:
            **data: Keyword arguments defining the agent run configuration per AgentRunRequestDict.
        
        Returns:
            AgentResponse: The response from executing the agent run request.
        """
        request = AgentRunRequest.model_validate(data)
        response = self.request(AgentsClient.agent_run_endpoint().with_request(request))
        self._last_agent_response = response
        return response

    def close(self, agent_id: str) -> AgentResponse:
        """
        Stops an agent and clears the stored agent state.
        
        Retrieves the effective agent identifier using the provided value or a previously stored response.
        Constructs and sends a stop request to the corresponding endpoint, resets the stored agent response,
        and returns the validated API response.
        
        Args:
            agent_id (str): The identifier of the agent to stop. If not valid, an identifier is retrieved
                            from the previous response.
        
        Returns:
            AgentResponse: The response from the agent stop operation.
        
        Raises:
            ValueError: If a valid agent identifier cannot be determined.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_stop_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = None
        return response

    def status(self, agent_id: str) -> AgentResponse:
        """
        Retrieves the status of the specified agent.
        
        This method validates the agent identifier (using a provided value or the last stored
        value), constructs the corresponding endpoint, and sends a request to the Notte API.
        It validates the response as an AgentResponse, updates the client's last agent response,
        and returns the status data.
        
        Raises:
            ValueError: If a valid agent identifier cannot be determined.
        
        Returns:
            AgentResponse: The validated response containing the agent's status.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_status_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[AgentResponse]:
        """
        List agents with optional filtering and pagination parameters.
        
        Validates the provided keyword arguments against the agent list criteria,
        constructs the endpoint, and retrieves a list of agents from the API.
        
        Keyword Args:
            **data: Options for filtering and pagination as defined in the list request schema.
        
        Returns:
            Sequence[AgentResponse]: A list of agent responses from the API.
        """
        params = AgentListRequest.model_validate(data)
        endpoint = AgentsClient.agent_list_endpoint(params=params)
        return self.request_list(endpoint)
