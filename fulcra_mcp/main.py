import json
import logging
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastmcp import FastMCP
from fastmcp.server.auth.auth import OAuthProvider
from fulcra_api.core import FulcraAPI
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.session import ServerSession
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

OIDC_SCOPES = ["openid", "profile", "name", "email"]


class Settings(BaseSettings):
    state_path: Path = Path("state/").resolve()
    oidc_server_url: str = "http://localhost:4499"
    fulcra_environment: str = "stdio"
    port: int = 4499
    oidc_client_id: str | None = None
    fulcra_oidc_domain: str | None = None
    fulcra_api: str | None = None


settings = Settings()

logger = structlog.getLogger(__name__)
if settings.fulcra_environment == "localdev":
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.DEBUG)


class FulcraOAuthProvider(OAuthProvider):
    def __init__(
        self,
        issuer_url: AnyHttpUrl | str,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
        required_scopes: list[str] | None = None,
    ):
        super().__init__(
            base_url=settings.oidc_server_url,
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
            required_scopes=required_scopes,
        )
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.state_mapping: dict[str, dict[str, str]] = {}
        self.token_mapping: dict[str, str] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get OAuth client information."""

        client_filepath = (settings.state_path / f"{client_id}.json").resolve()

        if not client_filepath.is_relative_to(settings.state_path):
            return None

        try:
            with client_filepath.open(mode="r") as c:
                return OAuthClientInformationFull.model_validate_json(c.read())
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error("Caught exception while loading client info", exc_info=exc)
            return None

    async def register_client(self, client_info: OAuthClientInformationFull):
        """Register a new OAuth client."""

        client_filepath = (
            settings.state_path / f"{client_info.client_id}.json"
        ).resolve()

        if not client_filepath.is_relative_to(settings.state_path):
            return None

        try:
            with client_filepath.open(mode="w") as c:
                c.write(client_info.model_dump_json())
        except Exception as exc:
            logger.error("Caught exception while writing client info", exc_info=exc)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        state = params.state or secrets.token_hex(16)
        self.state_mapping[state] = {
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": str(
                params.redirect_uri_provided_explicitly
            ),
            "client_id": client.client_id,
        }
        fulcra = FulcraAPI(
            oidc_client_id=settings.oidc_client_id,
            oidc_domain=settings.fulcra_oidc_domain,
            oidc_audience=settings.fulcra_api,
        )
        auth_url = fulcra.get_authorization_code_url(
            redirect_uri=f"{settings.oidc_server_url}/callback",
            state=state,
        )
        return auth_url

    async def handle_callback(self, code: str, state: str) -> str:
        state_data = self.state_mapping.get(state)
        if not state_data:
            raise HTTPException(400, "Invalid state parameter")

        redirect_uri = state_data["redirect_uri"]
        code_challenge = state_data["code_challenge"]
        redirect_uri_provided_explicitly = (
            state_data["redirect_uri_provided_explicitly"] == "True"
        )
        client_id = state_data["client_id"]

        fulcra = FulcraAPI(
            oidc_client_id=settings.oidc_client_id,
        )
        try:
            fulcra.authorize_with_authorization_code(
                code=code,
                redirect_uri=f"{settings.oidc_server_url}/callback",
            )
            access_token = fulcra.get_cached_access_token()
            new_code = f"mcp_{secrets.token_hex(16)}"
            # Create MCP authorization code
            auth_code = AuthorizationCode(
                code=new_code,
                client_id=client_id,
                redirect_uri=AnyHttpUrl(redirect_uri),
                redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
                expires_at=time.time() + 300,
                scopes=OIDC_SCOPES,
                code_challenge=code_challenge,
            )
            self.auth_codes[new_code] = auth_code
            self.tokens[access_token] = AccessToken(
                token=access_token,
                client_id=client_id,
                scopes=OIDC_SCOPES,
                expires_at=None,
            )
        except Exception as e:
            logger.error("oauth2 code exchange failure", exc_info=e)
            raise HTTPException(400, "failed to exchange code for token")

        del self.state_mapping[state]
        return construct_redirect_uri(redirect_uri, code=new_code, state=state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """Load an authorization code."""
        return self.auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")

        # Generate MCP access token
        mcp_token = f"mcp_{secrets.token_hex(32)}"

        # Store MCP token
        self.tokens[mcp_token] = AccessToken(
            token=mcp_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
        )

        # Find GitHub token for this client
        oidc_token = next(
            (
                token
                for token, data in self.tokens.items()
                # see https://github.blog/engineering/platform-security/behind-githubs-new-authentication-token-formats/
                # which you get depends on your GH app setup.
                if data.client_id == client.client_id
            ),
            None,
        )

        if oidc_token:
            self.token_mapping[mcp_token] = oidc_token

        del self.auth_codes[authorization_code.code]

        return OAuthToken(
            access_token=mcp_token,
            token_type="bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load and validate an access token."""
        access_token = self.tokens.get(token)
        if not access_token:
            return None

        # Check if expired
        if access_token.expires_at and access_token.expires_at < time.time():
            del self.tokens[token]
            return None

        return access_token

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """Load a refresh token - not supported."""
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Exchange refresh token"""
        raise NotImplementedError("Not supported")

    async def revoke_token(
        self, token: str, token_type_hint: str | None = None
    ) -> None:
        """Revoke a token."""
        if token in self.tokens:
            del self.tokens[token]


oauth_provider = FulcraOAuthProvider(
    issuer_url=AnyHttpUrl(settings.oidc_server_url),
    client_registration_options=ClientRegistrationOptions(
        enabled=True,
        valid_scopes=OIDC_SCOPES,
        default_scopes=OIDC_SCOPES,
    ),
    required_scopes=["openid"],
)
mcp = FastMCP(
    name="Fulcra Context Agent",
    instructions="""
    This server provides personal data retrieval tools.
    Always specify the time zone when using times as parameters.
    """,
    auth=oauth_provider,
)

stdio_fulcra: FulcraAPI | None = None


def get_fulcra_object() -> FulcraAPI:
    global stdio_fulcra

    if settings.fulcra_environment == "stdio":
        if stdio_fulcra is not None:
            return stdio_fulcra
        else:
            stdio_fulcra = FulcraAPI()
            stdio_fulcra.authorize()
            return stdio_fulcra

    mcp_access_token = get_access_token()
    if not mcp_access_token:
        raise HTTPException(401, "Not authenticated")
    fulcra_token = oauth_provider.token_mapping.get(mcp_access_token.token)
    if fulcra_token is None:
        raise HTTPException(401, "Not authenticated")
    fulcra = FulcraAPI()
    fulcra.set_cached_access_token(fulcra_token)
    return fulcra


def _coerce_bool_arg(
    value: bool | str | int | float | None,
    *,
    parameter_name: str,
) -> bool | None:
    """Normalize potentially string-encoded boolean arguments."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return False
        if value == 1:
            return True
        raise ValueError(
            f"Invalid boolean value for '{parameter_name}': {value!r}. Expected 0 or 1."
        )
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
        raise ValueError(
            f"Invalid boolean string for '{parameter_name}': {value!r}. Expected 'true', 'false', '1', or '0'."
        )
    raise ValueError(
        f"Unsupported type for '{parameter_name}': {type(value).__name__}. Expected bool, str, int, or float."
    )


def _coerce_float_arg(
    value: bool | str | int | float | None,
    *,
    parameter_name: str,
) -> float | None:
    """Normalize potentially string-encoded numeric arguments."""

    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                f"Invalid numeric string for '{parameter_name}': {value!r}. Expected a number."
            )
        try:
            return float(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid numeric string for '{parameter_name}': {value!r}. Expected a number."
            ) from exc
    raise ValueError(
        f"Unsupported type for '{parameter_name}': {type(value).__name__}. Expected bool, str, int, or float."
    )


def _coerce_list_arg(
    value: list | tuple | str | None,
    *,
    parameter_name: str,
    element_type: type,
) -> list | None:
    """Normalize list-like arguments that may be JSON-encoded strings."""

    if value is None:
        return None

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON for '{parameter_name}': {value!r}. Expected a JSON array."
            ) from exc
        if not isinstance(parsed, list):
            raise ValueError(
                f"Invalid JSON for '{parameter_name}': {value!r}. Expected a JSON array."
            )
        value = parsed

    if isinstance(value, tuple):
        value = list(value)

    if not isinstance(value, list):
        raise ValueError(
            f"Unsupported type for '{parameter_name}': {type(value).__name__}. Expected list, tuple, or JSON-encoded list."
        )

    def _is_valid_element(element) -> bool:
        if element_type is int:
            return isinstance(element, int) and not isinstance(element, bool)
        return isinstance(element, element_type)

    for index, element in enumerate(value):
        if not _is_valid_element(element):
            raise ValueError(
                f"Invalid element at index {index} for '{parameter_name}': {element!r}. Expected {element_type.__name__} values."
            )

    return value


@mcp.tool()
async def get_workouts(start_time: datetime, end_time: datetime) -> str:
    """Get details about the workouts that the user has done during a period of time.
    Result timestamps will include time zones. Always translate timestamps to the user's local
    time zone when this is known.

    Args:
        start_time: The starting time of the period. Must include tz (ISO8601).
        end_time: the ending time of the period. Must include tz (ISO8601).
    """
    fulcra = get_fulcra_object()
    workouts = fulcra.apple_workouts(start_time, end_time)
    return f"Workouts during {start_time} and {end_time}: " + json.dumps(workouts)


@mcp.tool()
async def get_metrics_catalog() -> str:
    """Get the catalog of available metrics that can be used in time-series API calls
    (`metric_time_series` and `metric_samples`).
    """
    fulcra = get_fulcra_object()
    catalog = fulcra.metrics_catalog()
    return "Available metrics: " + json.dumps(catalog)


@mcp.tool()
async def get_metric_time_series(
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
    sample_rate: float | int | str | None = None,
    replace_nulls: bool | str | None = None,
    calculations: list[str] | str | None = None,
) -> str:
    """Get user's time-series data for a single Fulcra metric.

    Covers the time starting at start_time (inclusive) until end_time (exclusive).
    Result timestamps will include tz. Always translate timestamps to the user's local
    tz when this is known.

    Args:
        metric_name: The name of the time-series metric to retrieve. Use `get_metrics_catalog` to find available metrics.
        start_time: The starting time period (inclusive). Must include tz (ISO8601).
        end_time: The ending time (exclusive). Must include tz (ISO8601).
        sample_rate: Optional. The number of seconds per sample. Defaults to 60 seconds when omitted.
        replace_nulls: Optional. When true, replace all NA with 0. Defaults to False when omitted.
        calculations: Optional. A list of additional calculations to perform for each
        time slice.  Not supported on cumulative metrics.  Options: "max", "min", "delta", "mean", "uniques", "allpoints", "rollingmean".
    Returns:
        A JSON string representing a list of data points for the metric.
        For time ranges where data is missing, the values will be NA unless replace_nulls is true.
    """
    fulcra = get_fulcra_object()
    # Ensure defaults are passed correctly if None
    kwargs = {}
    sample_rate_value = (
        60.0
        if sample_rate is None
        else _coerce_float_arg(sample_rate, parameter_name="sample_rate")
    )
    replace_nulls_value = (
        False
        if replace_nulls is None
        else _coerce_bool_arg(replace_nulls, parameter_name="replace_nulls")
    )
    if sample_rate_value is not None:
        kwargs["sample_rate"] = sample_rate_value
    if replace_nulls_value is not None:
        kwargs["replace_nulls"] = replace_nulls_value
    calculations_value = _coerce_list_arg(
        calculations,
        parameter_name="calculations",
        element_type=str,
    )
    if calculations_value is not None:
        kwargs["calculations"] = calculations_value

    time_series_df = fulcra.metric_time_series(
        metric=metric_name,
        start_time=start_time,
        end_time=end_time,
        **kwargs,
    )
    return (
        f"Time series data for {metric_name} from {start_time} to {end_time}: "
        + time_series_df.to_json(
            orient="records", date_format="iso", default_handler=str
        )
    )


@mcp.tool()
async def get_metric_samples(
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """Retrieve the raw samples related to a given metric for the user during a specified period.

    In cases where samples cover ranges and not points in time, a sample will be returned
    if any part of its range intersects with the requested range. For example, if start_time
    is 14:00 and end_time is 15:00, a sample covering 13:30-14:30 will be included.
    Result timestamps will include time zones. Always translate timestamps to the user's local
    time zone when this is known.

    Args:
        metric_name: The name of the metric to retrieve samples for. Use `get_metrics_catalog` to find available metrics.
        start_time: The start of the time range (inclusive), as an ISO 8601 string or datetime object.
        end_time: The end of the time range (exclusive), as an ISO 8601 string or datetime object.
    Returns:
        A JSON string representing a list of raw samples for the metric.
    """
    fulcra = get_fulcra_object()
    samples = fulcra.metric_samples(
        metric=metric_name,
        start_time=start_time,
        end_time=end_time,
    )
    return (
        f"Raw samples for {metric_name} from {start_time} to {end_time}: "
        + json.dumps(samples)
    )


@mcp.tool()
async def get_sleep_cycles(
    start_time: datetime,
    end_time: datetime,
    cycle_gap: str | None = None,
    stages: list[int] | str | None = None,
    gap_stages: list[int] | str | None = None,
    clip_to_range: bool | str | None = None,
) -> str:
    """Return sleep cycles summarized from sleep stages.

    Processes raw sleep data samples into sleep cycles by finding gaps in the
    sleep sample data within a specified time interval.
    Result timestamps will include time zones. Always translate timestamps to the user's local
    time zone when this is known.

    Args:
        start_time: The starting timestamp (inclusive), as an ISO 8601 string or datetime object.
        end_time: The ending timestamp (exclusive), as an ISO 8601 string or datetime object.
        cycle_gap: Optional. Minimum time interval separating distinct cycles (e.g., "PT2H" for 2 hours).
                   Defaults to server-side default if not provided.
        stages: Optional. Sleep stages to include. Defaults to all stages if not provided.
        gap_stages: Optional. Sleep stages to consider as gaps in sleep cycles.
                    Defaults to server-side default if not provided.
        clip_to_range: Optional. Whether to clip the data to the requested date range. Defaults to True when omitted.
    Returns:
        A JSON string representing a pandas DataFrame containing the sleep cycle data.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if cycle_gap is not None:
        kwargs["cycle_gap"] = cycle_gap
    stages_value = _coerce_list_arg(
        stages,
        parameter_name="stages",
        element_type=int,
    )
    if stages_value is not None:
        kwargs["stages"] = stages_value
    gap_stages_value = _coerce_list_arg(
        gap_stages,
        parameter_name="gap_stages",
        element_type=int,
    )
    if gap_stages_value is not None:
        kwargs["gap_stages"] = gap_stages_value
    clip_to_range_value = (
        True
        if clip_to_range is None
        else _coerce_bool_arg(clip_to_range, parameter_name="clip_to_range")
    )
    if clip_to_range_value is not None:
        kwargs["clip_to_range"] = clip_to_range_value

    sleep_cycles_df = fulcra.sleep_cycles(
        start_time=start_time,
        end_time=end_time,
        **kwargs,
    )
    # Convert DataFrame to JSON. `orient='records'` gives a list of dicts.
    # `date_format='iso'` ensures datetimes are ISO8601 strings.
    return f"Sleep cycles from {start_time} to {end_time}: " + sleep_cycles_df.to_json(
        orient="records", date_format="iso", default_handler=str
    )


@mcp.tool()
async def get_location_at_time(
    time: datetime,
    window_size: int = 14400,
    reverse_geocode: bool | str | None = None,
) -> str:
    """Gets the user's location at the given time.

    If no sample is available for the exact time, searches for the closest one up to
    window_size seconds back.

    Result timestamps will include time zones. Always translate timestamps to the user's local
    time zone when this is known.

    Args:
        time: The point in time to get the user's location for. Must include tz (ISO8601).
        window_size: Optional. The size (in seconds) to look back (and optionally forward) for samples. Defaults to 14400.
        include_after: Optional. When true, a sample that occurs after the requested time may be returned if it is the closest one. Defaults to False.
        reverse_geocode: Optional. When true, Fulcra will attempt to reverse geocode the location. Defaults to False when omitted.
    Returns:
        A JSON string representing the location data.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if window_size is not None:
        kwargs["window_size"] = window_size
    kwargs["include_after"] = True
    reverse_geocode_value = (
        False
        if reverse_geocode is None
        else _coerce_bool_arg(reverse_geocode, parameter_name="reverse_geocode")
    )
    if reverse_geocode_value is not None:
        kwargs["reverse_geocode"] = reverse_geocode_value

    location_data = fulcra.location_at_time(
        time=time,
        **kwargs,
    )
    return f"Location info at {time}: " + json.dumps(location_data)


@mcp.tool()
async def get_location_time_series(
    start_time: datetime,
    end_time: datetime,
    change_meters: float | int | str | None = None,
    sample_rate: int | float | str | None = None,
    reverse_geocode: bool | str | None = None,
) -> str:
    """Retrieve a time series of locations that the user was at.
    Result timestamps will include time zones. Always translate timestamps to the user's local tz when this is known.

    Args:
        start_time: The start of the time range (inclusive), as an ISO 8601 string or datetime object.
        end_time: The end of the range (exclusive), as an ISO 8601 string or datetime object.
        change_meters: Optional. When specified, subsequent samples that are fewer than this many meters away will not be included.
        sample_rate: Optional. The length (in seconds) of each sample. Defaults to 900 seconds when omitted.
        reverse_geocode: Optional. When true, Fulcra will attempt to reverse geocode the locations and include the details in the results. Defaults to False when omitted.
    Returns:
        A JSON string representing a list of location data points.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if change_meters is not None:
        kwargs["change_meters"] = _coerce_float_arg(
            change_meters, parameter_name="change_meters"
        )
    sample_rate_value = (
        900
        if sample_rate is None
        else _coerce_float_arg(sample_rate, parameter_name="sample_rate")
    )
    if sample_rate_value is not None:
        if float(sample_rate_value).is_integer():
            kwargs["sample_rate"] = int(sample_rate_value)
        else:
            kwargs["sample_rate"] = sample_rate_value
    kwargs["look_back"] = 14400
    reverse_geocode_value = (
        False
        if reverse_geocode is None
        else _coerce_bool_arg(reverse_geocode, parameter_name="reverse_geocode")
    )
    if reverse_geocode_value is not None:
        kwargs["reverse_geocode"] = reverse_geocode_value

    location_series = fulcra.location_time_series(
        start_time=start_time,
        end_time=end_time,
        **kwargs,
    )
    return f"Location time series from {start_time} to {end_time}: " + json.dumps(
        location_series
    )


@mcp.tool()
async def get_user_info() -> str:
    """Return general info about the Context by Fulcra user.

    Returns user references such as time zone, calendar ids, and other metadata.
    """
    fulcra = get_fulcra_object()
    user_info = fulcra.get_user_info()
    return "User information: " + json.dumps(user_info)


mcp_asgi_app = mcp.http_app(path="/")
app = FastAPI(lifespan=mcp_asgi_app.lifespan, debug=True)


@app.get("/callback")
async def callback_handler(request: Request) -> Response:
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(400, "Missing code or state parameter")

    try:
        redirect_uri = await oauth_provider.handle_callback(code, state)
        return RedirectResponse(status_code=302, url=redirect_uri)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error", exc_info=e)
    raise HTTPException(500, "Unexpected error")


# OpenAI sends an invalid token_endpoint_auth_method, so we ignore that with this
# middleware.
class OpenAIWorkaroundMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # logger.info(f"Request received (ASGI): method={scope['method']}, path={scope['path']}")

        if scope["path"] == "/register":
            logger.info(
                "Intercepted /register request (ASGI). Attempting to modify 'token_endpoint_auth_method'."
            )

            body_chunks = []
            more_body = True
            while more_body:
                message = await receive()
                if message["type"] != "http.request":
                    logger.warning(
                        f"Unexpected ASGI message type '{message['type']}' received while reading body for /register."
                    )

                    if (
                        not body_chunks and message.get("body") is None
                    ):  # No body part in first message
                        logger.warning(
                            "No body found in first message for /register. Bypassing modification."
                        )

                        # Need to make sure the message we just consumed is passed on
                        async def pass_through_receive():
                            yield message  # The message we just consumed
                            while True:
                                yield await (
                                    receive()
                                )  # Subsequent messages from original stream

                        await self.app(scope, pass_through_receive(), send)
                        return

                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)
                if message["type"] == "http.disconnect":  # Client disconnected
                    logger.warning(
                        "Client disconnected while reading body for /register."
                    )
                    return

            original_body_bytes = b"".join(body_chunks)
            new_body_bytes = original_body_bytes

            if original_body_bytes:
                try:
                    body_str = original_body_bytes.decode("utf-8")
                    data = json.loads(body_str)

                    if (
                        isinstance(data, dict)
                        and data.get("token_endpoint_auth_method")
                        == "client_secret_basic"
                    ):
                        data["token_endpoint_auth_method"] = "client_secret_post"
                        new_body_bytes = json.dumps(data).encode("utf-8")
                        # Removed the line: new_body_bytes = bytes() which was a bug
                        logger.info(
                            "Successfully modified 'token_endpoint_auth_method' to 'client_secret_post' for /register request (ASGI)."
                        )
                    else:
                        logger.info(
                            "'token_endpoint_auth_method' was not 'client_secret_basic' or key not present in /register request body (ASGI). No changes made."
                        )

                except json.JSONDecodeError:
                    logger.warning(
                        "Request body for /register was not valid JSON (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
                except UnicodeDecodeError:
                    logger.warning(
                        "Request body for /register could not be decoded as UTF-8 (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
                except Exception:
                    logger.error(
                        "An unexpected error occurred while trying to modify the request body for /register (ASGI). Proceeding with original body.",
                        exc_info=True,
                    )
            else:
                logger.info(
                    "Request body for /register is empty (ASGI). No modification attempted."
                )

            sent_synthetic_body = False

            async def new_receive_for_app():
                nonlocal sent_synthetic_body
                if not sent_synthetic_body:
                    sent_synthetic_body = True
                    return {
                        "type": "http.request",
                        "body": new_body_bytes,
                        "more_body": False,
                    }
                else:
                    return await receive()

            await self.app(scope, new_receive_for_app, send)

        else:
            await self.app(scope, receive, send)


app.add_middleware(OpenAIWorkaroundMiddleware)
app.mount("/", mcp_asgi_app)


old__received_request = ServerSession._received_request


async def _received_request(self, *args, **kwargs):
    try:
        return await old__received_request(self, *args, **kwargs)
    except RuntimeError:
        pass


# pylint: disable-next=protected-access
ServerSession._received_request = _received_request


def main():
    if settings.fulcra_environment == "stdio":
        mcp.run()
    else:
        settings.state_path.mkdir(parents=True, exist_ok=True)

        uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
