from typing import Self

from typing_extensions import final

from notte.sdk.endoints.agents import AgentsClient
from notte.sdk.endoints.env import EnvClient
from notte.sdk.endoints.sessions import SessionsClient


@final
class NotteClient:
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initializes the NotteClient with dedicated API client instances.
        
        Creates separate clients for session, agent, and environment management using the
        provided API key and server URL to interact with the Notte API.
        
        Args:
            api_key: Optional API key for authenticating with the Notte API.
            server_url: Optional base URL for the Notte API server.
        """
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, server_url=server_url)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, server_url=server_url)
        self.env: EnvClient = EnvClient(api_key=api_key, server_url=server_url)

    def local(self) -> Self:
        """
        Switches the client to local mode.
        
        Invokes the local() method on the sessions, agents, and environment clients,
        setting them to use local endpoints. Returns the current client instance.
        """
        _ = self.sessions.local()
        _ = self.agents.local()
        _ = self.env.local()
        return self

    def remote(self) -> Self:
        """
        Switches internal clients to remote mode.
        
        Calls the remote() method on the sessions, agents, and environment clients,
        configuring them for remote interactions. Returns the current instance.
        """
        _ = self.sessions.remote()
        _ = self.agents.remote()
        _ = self.env.remote()
        return self
