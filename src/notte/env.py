import asyncio
import datetime as dt
import sys
from collections.abc import Callable, Sequence
from typing import Self, Unpack

from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

from notte.actions.base import ExecutableAction
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.pool.base import BaseBrowserPool
from notte.browser.snapshot import BrowserSnapshot
from notte.browser.window import BrowserWindow, BrowserWindowConfig
from notte.common.config import FrozenConfig
from notte.common.logging import timeit
from notte.common.resource import AsyncResource
from notte.common.telemetry import capture_event, track_usage
from notte.controller.actions import (
    BaseAction,
    BrowserActionId,
    GotoAction,
    ScrapeAction,
    WaitAction,
)
from notte.controller.base import BrowserController
from notte.errors.env import MaxStepsReachedError, NoSnapshotObservedError
from notte.errors.processing import InvalidInternalCheckError
from notte.llms.engine import LlmModel
from notte.llms.service import LLMService
from notte.pipe.action.pipe import (
    MainActionSpaceConfig,
    MainActionSpacePipe,
)
from notte.pipe.preprocessing.pipe import (
    PreprocessingConfig,
    ProcessedSnapshotPipe,
)
from notte.pipe.resolution.pipe import NodeResolutionPipe
from notte.pipe.scraping.pipe import DataScrapingPipe, ScrapingConfig
from notte.sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    PaginationParams,
    PaginationParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
)


class ScrapeAndObserveParamsDict(ScrapeParamsDict, PaginationParamsDict):
    pass


class NotteEnvConfig(FrozenConfig):
    max_steps: int = DEFAULT_MAX_NB_STEPS
    preprocessing: PreprocessingConfig = PreprocessingConfig()
    window: BrowserWindowConfig = BrowserWindowConfig()
    scraping: ScrapingConfig = ScrapingConfig()
    action: MainActionSpaceConfig = MainActionSpaceConfig()
    observe_max_retry_after_snapshot_update: int = 2
    nb_seconds_between_snapshots_check: int = 10
    auto_scrape: bool = True
    perception_model: str | None = None
    verbose: bool = False
    structured_output_retries: int = 3

    def dev_mode(self: Self) -> Self:
        format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.configure(handlers=[dict(sink=sys.stderr, level="DEBUG", format=format)])  # type: ignore
        return self.set_deep_verbose()

    def user_mode(self: Self) -> Self:
        return self._copy_and_validate(
            verbose=True,
            window=self.window.set_verbose(),
            action=self.action.set_verbose(),
        )

    def agent_mode(self: Self) -> Self:
        format = "<level>{level: <8}</level> - <level>{message}</level>"
        logger.configure(handlers=[dict(sink=sys.stderr, level="INFO", format=format)])  # type: ignore
        return self.set_deep_verbose(False)

    def groq(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.groq)

    def openai(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.openai)

    def cerebras(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.cerebras)

    def gemini(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.gemini)

    def model(self: Self, model: str) -> Self:
        return self._copy_and_validate(perception_model=model)

    def a11y(self: Self) -> Self:
        return self._copy_and_validate(preprocessing=self.preprocessing.accessibility())

    def dom(self: Self) -> Self:
        return self._copy_and_validate(preprocessing=self.preprocessing.dom())

    def steps(self: Self, max_steps: int | None = None) -> Self:
        return self._copy_and_validate(max_steps=max_steps if max_steps is not None else DEFAULT_MAX_NB_STEPS)

    def headless(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(window=self.window.set_headless(value))

    def not_headless(self: Self) -> Self:
        return self._copy_and_validate(window=self.window.set_headless(False))

    def cdp(self: Self, url: str) -> Self:
        return self._copy_and_validate(window=self.window.set_cdp_url(url))

    def llm_action_tagging(self: Self) -> Self:
        return self._copy_and_validate(action=self.action.set_llm_tagging())

    def llm_data_extract(self: Self) -> Self:
        return self._copy_and_validate(scraping=self.scraping.set_llm_extract())

    def web_security(self: Self, value: bool = True) -> Self:
        if value:
            return self.enable_web_security()
        return self.disable_web_security()

    def disable_web_security(self: Self) -> Self:
        return self._copy_and_validate(window=self.window.disable_web_security())

    def enable_web_security(self: Self) -> Self:
        return self._copy_and_validate(window=self.window.enable_web_security())

    def disable_auto_scrape(self: Self) -> Self:
        return self._copy_and_validate(auto_scrape=False)

    def enable_auto_scrape(self: Self) -> Self:
        return self._copy_and_validate(auto_scrape=True)

    def use_llm(self: Self) -> Self:
        return self.llm_data_extract().llm_action_tagging()

    def disable_perception(self: Self) -> Self:
        return self._copy_and_validate(
            scraping=self.scraping.set_simple(),
            action=self.action.set_simple(),
        ).disable_auto_scrape()

    def set_structured_output_retries(self: Self, value: int) -> Self:
        return self._copy_and_validate(structured_output_retries=value)


class TrajectoryStep(BaseModel):
    obs: Observation
    action: BaseAction


class NotteEnv(AsyncResource):
    def __init__(
        self,
        config: NotteEnvConfig | None = None,
        window: BrowserWindow | None = None,
        pool: BaseBrowserPool | None = None,
        llmserve: LLMService | None = None,
        act_callback: Callable[[BaseAction, Observation], None] | None = None,
    ) -> None:
        """
        Initialize a NotteEnv instance with configuration and required services.
        
        If no configuration is provided, a default with LLM integration is used. This initializer
        sets up the browser window (optionally using a provided pool), controller, trajectory tracking,
        and processing pipes for actions, data scraping, and node resolution. An optional action callback
        can be specified to handle side effects upon executing actions. Telemetry is captured during
        initialization with key configuration parameters.
        """
        if config is not None:
            if config.verbose:
                logger.info(f"🔧 Custom notte-env config: \n{config.model_dump_json(indent=2)}")
        self.config: NotteEnvConfig = config or NotteEnvConfig().use_llm()
        if llmserve is None:
            llmserve = LLMService(
                base_model=self.config.perception_model, structured_output_retries=self.config.structured_output_retries
            )
        self._window: BrowserWindow = window or BrowserWindow(pool=pool, config=self.config.window)
        super().__init__(self._window)
        self.controller: BrowserController = BrowserController(self._window, verbose=self.config.verbose)

        self.trajectory: list[TrajectoryStep] = []
        self._snapshot: BrowserSnapshot | None = None
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve, config=self.config.action)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(
            llmserve=llmserve, window=self._window, config=self.config.scraping
        )
        self._node_resolution_pipe: NodeResolutionPipe = NodeResolutionPipe(
            window=self._window, type=self.config.preprocessing.type, verbose=self.config.verbose
        )
        self.act_callback: Callable[[BaseAction, Observation], None] | None = act_callback

        # Track initialization
        capture_event(
            "env.initialized",
            {
                "config": {
                    "perception_model": self.config.perception_model,
                    "auto_scrape": self.config.auto_scrape,
                    "headless": self.config.window.headless,
                    "preprocessing_type": self.config.preprocessing.type,
                }
            },
        )

    @property
    def snapshot(self) -> BrowserSnapshot:
        """
        Returns the current browser snapshot.
        
        Raises:
            NoSnapshotObservedError: If no snapshot has been observed.
        
        Returns:
            BrowserSnapshot: The most recent browser snapshot.
        """
        if self._snapshot is None:
            raise NoSnapshotObservedError()
        return self._snapshot

    @property
    def previous_actions(self) -> Sequence[BaseAction] | None:
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        if len(self.trajectory) <= 1:
            return None
        previous_obs: Observation = self.trajectory[-2].obs
        if not previous_obs.has_space():
            return None  # we don't have a space for pre-observations
        if self.obs.clean_url != previous_obs.clean_url:
            return None  # the page has significantly changed
        if previous_obs.space is None:
            raise InvalidInternalCheckError(
                check="Previous observation has no space. This should never happen.",
                url=previous_obs.metadata.url,
                dev_advice=(
                    "This technnically should never happen. There is likely an issue during the action space pipe."
                ),
            )
        return previous_obs.space.actions("all")

    @property
    def obs(self) -> Observation:
        if len(self.trajectory) <= 0:
            raise NoSnapshotObservedError()
        return self.trajectory[-1].obs

    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(
            max_steps=self.config.max_steps,
            current_step=len(self.trajectory),
        )

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot, action: BaseAction) -> Observation:
        if len(self.trajectory) >= self.config.max_steps:
            raise MaxStepsReachedError(max_steps=self.config.max_steps)
        self._snapshot = ProcessedSnapshotPipe.forward(snapshot, self.config.preprocessing)
        preobs = Observation.from_snapshot(snapshot, progress=self.progress())
        self.trajectory.append(TrajectoryStep(obs=preobs, action=action))
        if self.act_callback is not None:
            self.act_callback(action, preobs)
        return preobs

    async def _observe(
        self,
        pagination: PaginationParams,
        retry: int,
    ) -> Observation:
        """
        Asynchronously observes the current page and updates the observation as needed.
        
        This method processes the current page snapshot to extract the action space 
        using provided pagination settings. It checks if the snapshot is outdated by 
        comparing its timestamp with the current time. If the content has changed and 
        retries remain, it obtains a fresh snapshot and recursively re-observes the page.
        When auto-scrape is enabled and the observation lacks data, the method triggers 
        automatic data scraping.
        
        Args:
            pagination: Pagination settings used to extract available actions.
            retry: Number of remaining attempts to refresh the observation if outdated.
        
        Returns:
            The updated observation reflecting the current page state.
        """
        if self.config.verbose:
            logger.info(f"🧿 observing page {self.snapshot.metadata.url}")
        self.obs.space = self._action_space_pipe.forward(
            self.snapshot,
            self.previous_actions,
            pagination=pagination,
        )
        # TODO: improve this
        # Check if the snapshot has changed since the beginning of the trajectory
        # if it has, it means that the page was not fully loaded and that we should restart the oblisting
        time_diff = dt.datetime.now() - self.snapshot.metadata.timestamp
        if time_diff.total_seconds() > self.config.nb_seconds_between_snapshots_check:
            if self.config.verbose:
                logger.warning(
                    (
                        f"{time_diff.total_seconds()} seconds since the beginning of the action listing."
                        "Check if page content has changed..."
                    )
                )
            check_snapshot = await self._window.snapshot(screenshot=False)
            if not self.snapshot.compare_with(check_snapshot) and retry > 0:
                if self.config.verbose:
                    logger.warning(
                        "Snapshot changed since the beginning of the action listing, retrying to observe again"
                    )
                _ = self._preobserve(check_snapshot, action=WaitAction(time_ms=int(time_diff.total_seconds() * 1000)))
                return await self._observe(retry=retry - 1, pagination=pagination)

        if (
            self.config.auto_scrape
            and self.obs.space.category is not None
            and self.obs.space.category.is_data()
            and not self.obs.has_data()
        ):
            if self.config.verbose:
                logger.info(f"🛺 Autoscrape enabled and page is {self.obs.space.category}. Scraping page...")
            self.obs.data = await self._data_scraping_pipe.forward(self.snapshot, ScrapeParams())
        return self.obs

    @timeit("goto")
    @track_usage("env.goto")
    async def goto(self, url: str | None) -> Observation:
        """
        Navigate to the specified URL and return an updated observation.
        
        This asynchronous method directs the browser window to navigate to the given URL,
        captures a snapshot of the resulting page, and generates an observation enhanced with
        a goto action that records the navigated URL.
        
        Args:
            url: The URL to navigate to. If None, the browser's default navigation behavior applies.
        
        Returns:
            An Observation representing the state of the page after navigation.
        """
        snapshot = await self._window.goto(url)
        return self._preobserve(snapshot, action=GotoAction(url=snapshot.metadata.url))

    @timeit("observe")
    @track_usage("env.observe")
    async def observe(
        self,
        url: str | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        """
        Navigates to a URL (if provided) and observes the current page state.
        
        This method directs the environment to the specified URL using the goto() method,
        then captures a new observation of the page. It validates any given pagination 
        parameters and invokes the internal _observe() method with a retry setting from the 
        configuration. When verbose mode is enabled, debug logs for previous actions and 
        snapshot node IDs are recorded.
        
        Args:
            url: Optional URL to navigate to before capturing the observation.
            **pagination: Additional pagination parameters used to validate internal pagination
                          rules during the observation.
        
        Returns:
            The captured Observation of the current page.
        """
        _ = await self.goto(url)
        if self.config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationParams.model_validate(pagination),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("execute")
    @track_usage("env.execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        """
        Executes the specified action and returns the resulting observation.
        
        If the given action identifier corresponds to a scrape operation, this method
        delegates to the scrape routine. Otherwise, it parses the action using the
        provided parameters and optional enter flag, resolves the executable action via
        the node resolution pipeline, executes it, and prepares an observation based on
        the resulting snapshot.
        
        Args:
            action_id: Identifier for the action to execute. If it matches the scrape action,
                the scraping routine is invoked.
            params: Optional parameters for the action, either as a mapping or a string.
            enter: Optional flag indicating whether to engage additional action behavior.
        
        Returns:
            An observation capturing the state after executing the action.
        """
        if action_id == BrowserActionId.SCRAPE.value:
            # Scrape action is a special case
            return await self.scrape()
        exec_action = ExecutableAction.parse(action_id, params, enter=enter)
        action = await self._node_resolution_pipe.forward(exec_action, self._snapshot)
        snapshot = await self.controller.execute(action)
        obs = self._preobserve(snapshot, action=action)
        return obs

    @timeit("act")
    @track_usage("env.act")
    async def act(
        self,
        action: BaseAction,
    ) -> Observation:
        """
        Executes a provided action and returns an updated page observation.
        
        If the action is a scrape action, this method triggers a combined scraping and
        observation process using the action's instructions. For other actions, it resolves
        the action based on the current snapshot, executes it, and subsequently observes the
        updated page state.
        
        Parameters:
            action (BaseAction): The action to perform. For scrape actions, its instructions
                are used to initiate the combined scraping and observation process.
        
        Returns:
            Observation: The observation reflecting the page state after executing the action.
        """
        if self.config.verbose:
            logger.info(f"🌌 starting execution of action {action.id}...")
        if isinstance(action, ScrapeAction):
            # Scrape action is a special case
            # TODO: think about flow. Right now, we do scraping and observation in one step
            return await self.god(instructions=action.instructions)
        action = await self._node_resolution_pipe.forward(action, self._snapshot)
        snapshot = await self.controller.execute(action)
        if self.config.verbose:
            logger.info(f"🌌 action {action.id} executed in browser. Observing page...")
        _ = self._preobserve(snapshot, action=action)
        return await self._observe(
            pagination=PaginationParams(),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("step")
    @track_usage("env.step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        """
        Executes the specified action and returns an updated observation.
        
        This coroutine first executes the action identified by the provided ID with any 
        optional parameters. If verbose logging is enabled, it logs identifiers of previous 
        actions and elements in the current snapshot. Pagination parameters are then validated 
        and passed to the observation routine, which applies a retry limit based on the configuration.
        
        Args:
            action_id: Unique identifier for the action to execute.
            params: Optional additional parameters for the action, provided as a dict or string.
            enter: Optional flag to modify action behavior, such as simulating an enter command.
            **pagination: Keyword arguments controlling pagination, validated against PaginationParams.
        
        Returns:
            An Observation object representing the environment state after the action.
        """
        _ = await self.execute(action_id, params, enter=enter)
        if self.config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationParams.model_validate(pagination),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("scrape")
    @track_usage("env.scrape")
    async def scrape(
        self,
        url: str | None = None,
        **scrape_params: Unpack[ScrapeParamsDict],
    ) -> Observation:
        """
        Scrapes data from the current or a specified page.
        
        If a URL is provided, the function navigates to that URL before scraping. It then applies the provided scraping parameters to extract data from the page's snapshot and updates the current observation accordingly.
        
        Returns:
            Observation: The updated observation containing the scraped data.
        """
        if url is not None:
            _ = await self.goto(url)
        params = ScrapeParams(**scrape_params)
        self.obs.data = await self._data_scraping_pipe.forward(self.snapshot, params)
        return self.obs

    @timeit("god")
    @track_usage("env.god")
    async def god(
        self,
        url: str | None = None,
        **params: Unpack[ScrapeAndObserveParamsDict],
    ) -> Observation:
        """Activate God mode to perform concurrent scraping and action listing.
        
        If a URL is provided, the method navigates to that address before executing both a data scrape 
        and an action space retrieval concurrently. It validates the provided parameters as both 
        scraping and pagination configurations, executes the operations in parallel, updates the 
        current observation with the retrieved action space and scraped data, and returns the updated observation.
        
        Args:
            url (str, optional): URL to navigate to prior to performing scraping and action listing.
            **params: Additional parameters for scraping and pagination (ScrapeAndObserveParamsDict).
        
        Returns:
            Observation: The updated observation containing the extracted action space and scraped data.
        """
        if self.config.verbose:
            logger.info("🌊 God mode activated (scraping + action listing)")
        if url is not None:
            _ = await self.goto(url)
        scrape = ScrapeParams.model_validate(params)
        pagination = PaginationParams.model_validate(params)
        space, data = await asyncio.gather(
            self._action_space_pipe.forward_async(
                self.snapshot, previous_action_list=self.previous_actions, pagination=pagination
            ),
            self._data_scraping_pipe.forward_async(self.snapshot, scrape),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    @track_usage("env.reset")
    @override
    async def reset(self) -> None:
        """
        Resets the environment state.
        
        Clears the stored trajectory and snapshot, then resets the underlying browser window.
        Logs the reset operation if verbose mode is enabled.
        """
        if self.config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = []
        self._snapshot = None
        # reset the window
        await super().reset()
