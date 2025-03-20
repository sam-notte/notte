import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, Literal, Self, TypeVar

import requests
from loguru import logger
from pydantic import BaseModel

from notte.errors.sdk import AuthenticationError, NotteAPIError

TResponse = TypeVar("TResponse", bound=BaseModel, covariant=True)


class NotteEndpoint(BaseModel, Generic[TResponse]):
    path: str
    response: type[TResponse]
    request: BaseModel | None = None
    method: Literal["GET", "POST", "DELETE"]
    params: BaseModel | None = None

    def with_request(self, request: BaseModel) -> Self:
        # return deep copy of self with the request set
        """Return a new instance with the request model set.
        
        Creates and returns a deep copy of the current endpoint with its `request`
        attribute updated to the provided Pydantic model.
        
        Args:
            request: A Pydantic model representing the request payload.
        """
        return self.model_copy(update={"request": request})

    def with_params(self, params: BaseModel) -> Self:
        # return deep copy of self with the params set
        """
        Creates a new endpoint instance with updated parameters.
        
        Returns a deep copy of the current endpoint with its 'params' attribute set to
        the provided Pydantic model.
        
        Args:
            params: A Pydantic BaseModel instance containing the new parameters.
        
        Returns:
            A new instance of the endpoint with the updated parameters.
        """
        return self.model_copy(update={"params": params})


class BaseClient(ABC):
    DEFAULT_SERVER_URL: ClassVar[str] = "https://api.notte.cc"
    LOCAL_SERVER_URL: ClassVar[str] = "http://localhost:8000"

    def __init__(
        self,
        base_endpoint_path: str | None,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initialize a new BaseClient instance.
        
        Retrieves the API key either from the provided argument or from the
        "NOTTE_API_KEY" environment variable, raising an AuthenticationError if
        absent. Sets the server URL to the provided value or to DEFAULT_SERVER_URL
        if unspecified, stores an optional base endpoint path, and builds a mapping
        of endpoint paths to their corresponding NotteEndpoint instances.
        
        Args:
            base_endpoint_path: Optional base path for the API endpoints.
            api_key: Optional API key for authentication; if not provided, the key is
                obtained from the "NOTTE_API_KEY" environment variable.
            server_url: Optional server URL; defaults to DEFAULT_SERVER_URL if omitted.
        
        Raises:
            AuthenticationError: If no API key is supplied either via the argument or
                the environment.
        """
        token = api_key or os.getenv("NOTTE_API_KEY")
        if token is None:
            raise AuthenticationError("NOTTE_API_KEY needs to be provided")
        self.token: str = token
        self.server_url: str = server_url or self.DEFAULT_SERVER_URL
        self._endpoints: dict[str, NotteEndpoint[BaseModel]] = {
            endpoint.path: endpoint for endpoint in self.endpoints()
        }
        self.base_endpoint_path: str | None = base_endpoint_path

    def local(self) -> Self:
        """
        Switches the client to use the local server.
        
        Sets the client's server URL to the local endpoint and returns the updated instance for method chaining.
        """
        self.server_url = self.LOCAL_SERVER_URL
        return self

    def remote(self) -> Self:
        """
        Switches the client to use the default remote server.
        
        Sets the server URL to the predefined default and returns the client instance,
        allowing for method chaining.
        """
        self.server_url = self.DEFAULT_SERVER_URL
        return self

    @staticmethod
    @abstractmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Return a sequence of API endpoints for the client.
        
        Subclasses should override this method to provide the available API endpoints.
        Each endpoint is represented by a NotteEndpoint, which includes details such as
        the endpoint path, HTTP method, expected response model, and optional request or
        parameter data.
        """
        pass

    def headers(self) -> dict[str, str]:
        """
        Generates HTTP authorization headers.
        
        Returns:
            dict[str, str]: A dictionary with the 'Authorization' header formatted as 'Bearer <token>'.
        """
        return {"Authorization": f"Bearer {self.token}"}

    def request_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        """
        Constructs the full request URL for the given API endpoint.
        
        The URL is built by combining the client's server URL with the endpoint's path. If a base
        endpoint path is defined, it is inserted between the server URL and the endpoint's path.
        
        Args:
            endpoint: The API endpoint instance containing the relative path.
        
        Returns:
            The complete URL as a string.
        """
        if self.base_endpoint_path is None:
            return f"{self.server_url}/{endpoint.path}"
        return f"{self.server_url}/{self.base_endpoint_path}/{endpoint.path}"

    def _request(self, endpoint: NotteEndpoint[TResponse]) -> requests.Response:
        """
        Performs an HTTP request for the given API endpoint.
        
        The function constructs the request URL and headers, and executes a GET, POST, or DELETE
        operation based on the endpoint's method. For POST requests, it serializes the request model
        to JSON; if no request model is provided for a POST request, a ValueError is raised.
        After receiving a response, it attempts to parse the content as JSON and raises a NotteAPIError
        if the response status is not 200 or if the parsed JSON includes an error detail.
        
        Args:
            endpoint: A NotteEndpoint instance containing details such as method, path,
                optional request body, and query parameters.
        
        Raises:
            ValueError: If a POST request is made without a request model.
            NotteAPIError: If the response status code is not 200 or the JSON response contains an error detail.
        
        Returns:
            The parsed JSON response from the HTTP request.
        """
        headers = self.headers()
        url = self.request_path(endpoint)
        params = endpoint.params.model_dump() if endpoint.params is not None else None
        logger.info(
            f"Making `{endpoint.method}` request to `{endpoint.path} (i.e `{url}`) with params `{params}` and request `{endpoint.request}`"
        )
        match endpoint.method:
            case "GET":
                response = requests.get(url=url, headers=headers, params=params)
            case "POST":
                if endpoint.request is None:
                    raise ValueError("Request model is required for POST requests")
                response = requests.post(
                    url=url,
                    headers=headers,
                    json=endpoint.request.model_dump(),
                    params=params,
                )
            case "DELETE":
                response = requests.delete(
                    url=url,
                    headers=headers,
                    params=params,
                )
        response_dict: Any = response.json()
        if response.status_code != 200 or "detail" in response_dict:
            raise NotteAPIError(path=endpoint.path, response=response)
        return response_dict

    def request(self, endpoint: NotteEndpoint[TResponse]) -> TResponse:
        """
        Sends an API request to the endpoint and validates the response.
        
        Delegates the HTTP call to the internal _request method. If the returned
        response is not a dictionary, a NotteAPIError is raised with the endpoint path
        and raw response data. If the response is a dictionary, it is validated using
        the endpoint's expected model and the resulting model instance is returned.
        
        Args:
            endpoint: API endpoint specification including request details and the
                      expected response model.
        
        Raises:
            NotteAPIError: If the HTTP response is not a dictionary.
        
        Returns:
            The validated response model instance.
        """
        response: Any = self._request(endpoint)
        if not isinstance(response, dict):
            raise NotteAPIError(path=endpoint.path, response=response)
        return endpoint.response.model_validate(response)

    def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        # Handle the case where TResponse is a list of BaseModel
        """
        Send API request for an endpoint expecting a list response.
        
        This method performs an HTTP request using the specified endpoint and validates that the
        response is a list. If the response is not a list, it raises a NotteAPIError. Otherwise, each
        item in the response is validated against the endpoint's expected response model, and the
        validated items are returned as a sequence.
        
        Args:
            endpoint: An instance of NotteEndpoint specifying the API endpoint details.
        
        Returns:
            A sequence of validated response models of type TResponse.
        
        Raises:
            NotteAPIError: If the API response is not a list.
        """
        response_list: Any = self._request(endpoint)
        if not isinstance(response_list, list):
            raise NotteAPIError(path=endpoint.path, response=response_list)
        return [endpoint.response.model_validate(item) for item in response_list]  # pyright: ignore[reportUnknownVariableType]
