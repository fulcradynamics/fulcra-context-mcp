from datetime import datetime
import json
from enum import Enum

from fastmcp import FastMCP
from mcp.server.auth.middleware.auth_context import get_access_token

from .credentials import get_fulcra_object
from .provider import oauth_provider

tools_mcp = FastMCP(name="Fulcra Context Tools")


class AnnotationType(Enum):
    Moment = "moment"
    Duration = "duration"
    Boolean = "boolean"
    Numeric = "numeric"
    Scale = "scale"


@tools_mcp.tool()
async def get_annotations(
    ann_type: str | AnnotationType, start_time: datetime, end_time: datetime
) -> str:
    """
    Retrieve an array of all moment annotations the user recorded during a period of time.
    Each item contains the value (except for moment annotations) and the metadata (name, original spec, etc.) describing the annotation.

    Args:
        ann_type: annotation type (moment, duration, boolean, numeric, scale, etc.)
        start_time: The starting time of the period. Must include tz (ISO8601).
        end_time: the ending time of the period. Must include tz (ISO8601).
    """
    fulcra = get_fulcra_object()
    if not isinstance(ann_type, AnnotationType):
        try:
            ann_type = AnnotationType(ann_type)
        except ValueError:
            return f"Unknown annotation type. Current valid types: {' '.join([x.name for x in AnnotationType])}"
    match ann_type:
        case AnnotationType.Moment:
            annotations = fulcra.moment_annotations(start_time, end_time)
            return f"Moment annotations during {start_time} and {end_time}: {json.dumps(annotations)}"
        case AnnotationType.Duration:
            annotations = fulcra.duration_annotations(start_time, end_time)
            return f"Duration annotations during {start_time} and {end_time}: {json.dumps(annotations)}"
        case AnnotationType.Boolean:
            annotations = fulcra.boolean_annotations(start_time, end_time)
            return f"Boolean annotations during {start_time} and {end_time}: {json.dumps(annotations)}"
        case AnnotationType.Numeric:
            annotations = fulcra.numeric_annotations(start_time, end_time)
            return f"Numeric annotations during {start_time} and {end_time}: {json.dumps(annotations)}"
        case AnnotationType.Scale:
            annotations = fulcra.scale_annotations(start_time, end_time)
            return f"Scale annotations during {start_time} and {end_time}: {json.dumps(annotations)}"
        case _:
            return f"Unknown annotation type. Current valid types: {' '.join([x.name for x in AnnotationType])}"


@tools_mcp.tool()
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


@tools_mcp.tool()
async def annotations_catalog() -> str:
    """
    Get the list of all annotations the user has defined. This does not get the
    actual values the user has recorded; for that, use the `get_annotations` tool.
    Use this tool to get the IDs and types to pass to `get_annotations`.
    """
    fulcra = get_fulcra_object()
    catalog = fulcra.annotations_catalog()
    return "Defined annotations: " + json.dumps(catalog)


@tools_mcp.tool()
async def get_metrics_catalog() -> str:
    """Get the catalog of available metrics that can be used in time-series API calls
    (`metric_time_series` and `metric_samples`).
    """
    fulcra = get_fulcra_object()
    catalog = fulcra.metrics_catalog()
    return "Available metrics: " + json.dumps(catalog)


@tools_mcp.tool()
async def get_metric_time_series(
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
    sample_rate: float | None = 60.0,
    replace_nulls: bool | None = False,
    calculations: list[str] | None = None,
) -> str:
    """Get user's time-series data for a single Fulcra metric.

    Covers the time starting at start_time (inclusive) until end_time (exclusive).
    Result timestamps will include tz. Always translate timestamps to the user's local
    tz when this is known.

    Args:
        metric_name: The name of the time-series metric to retrieve. Use `get_metrics_catalog` to find available metrics.
        start_time: The starting time period (inclusive). Must include tz (ISO8601).
        end_time: The ending time (exclusive). Must include tz (ISO8601).
        sample_rate: Optional. The number of seconds per sample. Default is 60. Can be smaller than 1.
        replace_nulls: Optional. When true, replace all NA with 0. Default is False.
        calculations: Optional. A list of additional calculations to perform for each
        time slice.  Not supported on cumulative metrics.  Options: "max", "min", "delta", "mean", "uniques", "allpoints", "rollingmean".
    Returns:
        A JSON string representing a list of data points for the metric.
        For time ranges where data is missing, the values will be NA unless replace_nulls is true.
    """
    fulcra = get_fulcra_object()
    # Ensure defaults are passed correctly if None
    kwargs = {}
    if sample_rate is not None:
        kwargs["sample_rate"] = sample_rate
    if replace_nulls is not None:
        kwargs["replace_nulls"] = replace_nulls
    if calculations is not None:
        kwargs["calculations"] = calculations

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


@tools_mcp.tool()
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


@tools_mcp.tool()
async def get_sleep_cycles(
    start_time: datetime,
    end_time: datetime,
    cycle_gap: str | None = None,
    stages: list[int] | None = None,
    gap_stages: list[int] | None = None,
    clip_to_range: bool | None = True,
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
        clip_to_range: Optional. Whether to clip the data to the requested date range. Defaults to True.
    Returns:
        A JSON string representing a pandas DataFrame containing the sleep cycle data.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if cycle_gap is not None:
        kwargs["cycle_gap"] = cycle_gap
    if stages is not None:
        kwargs["stages"] = stages
    if gap_stages is not None:
        kwargs["gap_stages"] = gap_stages
    if clip_to_range is not None:
        kwargs["clip_to_range"] = clip_to_range

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


@tools_mcp.tool()
async def get_location_at_time(
    time: datetime,
    window_size: int = 14400,
    reverse_geocode: bool | None = False,
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
    Returns:
        A JSON string representing the location data.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if window_size is not None:
        kwargs["window_size"] = window_size
    kwargs["include_after"] = True
    kwargs["reverse_geocode"] = True

    location_data = fulcra.location_at_time(
        time=time,
        **kwargs,
    )
    return f"Location info at {time}: " + json.dumps(location_data)


@tools_mcp.tool()
async def get_location_time_series(
    start_time: datetime,
    end_time: datetime,
    change_meters: float | None = None,
    sample_rate: int | None = 900,
    reverse_geocode: bool | None = False,
) -> str:
    """Retrieve a time series of locations that the user was at.
    Result timestamps will include time zones. Always translate timestamps to the user's local tz when this is known.

    Args:
        start_time: The start of the time range (inclusive), as an ISO 8601 string or datetime object.
        end_time: The end of the range (exclusive), as an ISO 8601 string or datetime object.
        change_meters: Optional. When specified, subsequent samples that are fewer than this many meters away will not be included.
        sample_rate: Optional. The length (in seconds) of each sample. Default is 900.
        reverse_geocode: Optional. When true, Fulcra will attempt to reverse geocode the locations and include the details in the results. Default is False.
    Returns:
        A JSON string representing a list of location data points.
    """
    fulcra = get_fulcra_object()
    kwargs = {}
    if change_meters is not None:
        kwargs["change_meters"] = change_meters
    if sample_rate is not None:
        kwargs["sample_rate"] = sample_rate
    kwargs["look_back"] = 14400
    if reverse_geocode is not None:
        kwargs["reverse_geocode"] = reverse_geocode

    location_series = fulcra.location_time_series(
        start_time=start_time,
        end_time=end_time,
        **kwargs,
    )
    return f"Location time series from {start_time} to {end_time}: " + json.dumps(
        location_series
    )


@tools_mcp.tool()
async def debug_token_info() -> str:
    """Return info about the current MCP session's OAuth token.

    Shows scopes, expiry, client ID, and whether a Fulcra API token is mapped.
    Useful for diagnosing authentication and scope issues.
    """
    mcp_access_token = get_access_token()
    if not mcp_access_token:
        return json.dumps({"error": "No token in current session"})
    stored = oauth_provider.tokens.get(mcp_access_token.token)
    creds = oauth_provider.token_mapping.get(mcp_access_token.token)
    return json.dumps(
        {
            "client_id": stored.client_id if stored else None,
            "scopes": stored.scopes if stored else None,
            "mcp_token_expires_at": stored.expires_at if stored else None,
            "has_fulcra_credentials": creds is not None,
            "fulcra_token_expires_at": str(creds.access_token_expiration)
            if creds
            else None,
            "fulcra_has_refresh_token": bool(creds.refresh_token) if creds else None,
            "fulcra_token_expired": creds.is_expired() if creds else None,
            "mcp_token_prefix": mcp_access_token.token[:12],
        }
    )


@tools_mcp.tool()
async def get_user_info() -> str:
    """Return general info about the Context by Fulcra user.

    Returns user references such as time zone, calendar ids, and other metadata.
    """
    fulcra = get_fulcra_object()
    user_info = fulcra.get_user_info()
    return "User information: " + json.dumps(user_info)
