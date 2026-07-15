import base64
from datetime import datetime
import json
import re
import urllib.error
from enum import Enum
from pathlib import PurePath
from typing import Literal
from uuid import UUID

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


# Base annotation types; ids rooted in one of these (including custom
# "<Base>/<uuid>" types) are readable with the `get_annotations` tool.
ANNOTATION_BASE_TYPES = tuple(f"{t.name}Annotation" for t in AnnotationType)

NO_TOOL_GROUP = "data types not yet readable through this server"


def _compatible_tools(entry: dict) -> str:
    """Map a v1 catalog entry to the MCP tools that can read it, mirroring the
    CLI's related_cli_commands()."""
    if entry.get("queryable") is False:
        return "data types that cannot be queried (used only when recording data)"
    if entry.get("api_version") == "v0":
        if entry.get("class") == "metric":
            return "data types usable with: get_metric_time_series | get_records"
        if entry.get("class") == "location":
            return "data types usable with: get_location_at_time | get_location_time_series"
    if entry.get("id", "").startswith(ANNOTATION_BASE_TYPES):
        return "data types usable with: get_records | get_annotations (pass the ann_type matching the base type)"
    if entry.get("api_version") == "v1alpha1":
        return "data types usable with: get_records"
    return NO_TOOL_GROUP


def _slim_entry(entry: dict) -> dict:
    """Strip a v1 catalog entry down to the fields an MCP client needs."""
    record_spec = entry.get("record_spec") or {}
    slim = {"id": entry["id"]}
    if entry.get("name") and entry["name"] != entry["id"]:
        slim["name"] = entry["name"]
    if entry.get("description"):
        slim["description"] = re.sub(r"\s+", " ", entry["description"]).strip()
    if record_spec.get("unit") or entry.get("unit"):
        slim["unit"] = record_spec.get("unit") or entry.get("unit")
    if entry.get("metric_kind"):
        slim["kind"] = entry["metric_kind"]
    if entry.get("categories"):
        slim["categories"] = entry["categories"]
    if record_spec.get("scale"):
        slim["scale"] = record_spec["scale"]
    if record_spec.get("value_map"):
        slim["value_map"] = record_spec["value_map"]
    if entry.get("recordable") is False:
        slim["recordable"] = False
    return slim


@tools_mcp.tool()
async def get_data_catalog(
    data_type: str | None = None,
    category: str | None = None,
    name: str | None = None,
) -> str:
    """Get the catalog of all data types available for this user, grouped by the
    MCP tools that can read each type. Includes health/sensor metrics, location,
    events, and user-defined annotation types.

    Call this before requesting time-series data or raw records, and only use a
    data type with the tools named in its group.

    Args:
        data_type: Optional. Return only the data type with this exact ID.
        category: Optional. Filter by category (e.g. "healthkit", "annotations",
            "sleep", "mindfulness", "user_configured", "base_type").
        name: Optional. Filter results by partial, case-insensitive name match.
    """
    fulcra = get_fulcra_object()
    try:
        catalog = fulcra.v1_catalog(data_type=data_type, category=category)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"No data type found with ID {data_type!r}. Call get_data_catalog without arguments to list all available types."
        raise
    if name:
        catalog = [e for e in catalog if name.lower() in (e.get("name") or "").lower()]
    grouped: dict[str, list[dict]] = {}
    for entry in catalog:
        grouped.setdefault(_compatible_tools(entry), []).append(_slim_entry(entry))
    return "Available data types, grouped by compatible tool: " + json.dumps(grouped)


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

    Only data types that `get_data_catalog` lists as usable with this tool are
    supported; other types can be read with `get_records`.

    Args:
        metric_name: The name of the time-series metric to retrieve. Use `get_data_catalog` to find available metrics.
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

    try:
        time_series_df = fulcra.metric_time_series(
            metric=metric_name,
            start_time=start_time,
            end_time=end_time,
            **kwargs,
        )
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 422):
            return (
                f"Could not retrieve {metric_name!r} (HTTP {e.code}). Only data types "
                "that get_data_catalog lists under get_metric_time_series are supported "
                "by this tool; other types can be read with get_records."
            )
        raise
    return (
        f"Time series data for {metric_name} from {start_time} to {end_time}: "
        + time_series_df.to_json(
            orient="records", date_format="iso", default_handler=str
        )
    )


@tools_mcp.tool()
async def get_records(
    data_type: str,
    start_time: datetime,
    end_time: datetime,
    fulcra_userid: str | None = None,
) -> str:
    """Retrieve the raw records of a data type for the user during a specified period.

    Works with every data type listed by `get_data_catalog`, including
    user-defined ones, which use the "<BaseType>/<uuid>" ID form. The correct
    API endpoint is chosen automatically based on the catalog.

    In cases where records cover ranges and not points in time, a record will be
    returned if any part of its range intersects with the requested range. For
    example, if start_time is 14:00 and end_time is 15:00, a record covering
    13:30-14:30 will be included. Result timestamps will include time zones.
    Always translate timestamps to the user's local time zone when this is known.

    Returned records are raw samples: they may come from multiple sources and can
    overlap. For calculated per-interval values of numeric metrics, prefer
    `get_metric_time_series`.

    Args:
        data_type: The ID of the data type to retrieve, as returned by `get_data_catalog`.
        start_time: The start of the time range (inclusive). Must include tz (ISO8601).
        end_time: The end of the time range (exclusive). Must include tz (ISO8601).
        fulcra_userid: Optional. Retrieve data for another Fulcra user (requires
            an active datashare from that user).
    Returns:
        A JSON string representing a list of raw records for the data type.
    """
    fulcra = get_fulcra_object()

    # Support the "<BaseType>/<uuid>" shorthand for user-defined data types.
    base_type, _, user_annotation_id = data_type.partition("/")
    if user_annotation_id:
        try:
            user_annotation_id = str(UUID(user_annotation_id))
        except ValueError:
            return (
                "User-defined data type IDs must take the form <BaseType>/<UUID>. "
                "Use get_data_catalog to list valid IDs."
            )

    try:
        catalog_entries = fulcra.v1_catalog(data_type=base_type)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"No data type found with ID {data_type!r}. Use get_data_catalog to list available types."
        raise

    results = []
    for entry in catalog_entries:
        record_type = (entry.get("record_spec") or {}).get("type")
        if entry.get("api_version") == "v0" and record_type == "metric":
            kwargs = {
                "start_time": start_time,
                "end_time": end_time,
                "metric": entry["id"],
            }
            if fulcra_userid:
                kwargs["fulcra_userid"] = fulcra_userid
            results += fulcra.metric_samples(**kwargs)
        elif entry.get("api_version") == "v1alpha1" and record_type in (
            "metric",
            "event",
        ):
            path_type = entry["id"]
            if user_annotation_id:
                path_type = f"{path_type}/{user_annotation_id}"
            params = {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            }
            if fulcra_userid:
                params["fulcra_userid"] = fulcra_userid
            results += json.loads(fulcra.fulcra_v1_api(record_type, path_type, params))
        else:
            return (
                f"Could not derive an API endpoint for data type {entry['id']!r}. "
                "Use get_data_catalog to see which tools can read each data type."
            )
    return f"Records for {data_type} from {start_time} to {end_time}: " + json.dumps(
        results
    )


@tools_mcp.tool()
async def get_data_updates(
    start_time: datetime,
    end_time: datetime,
) -> str:
    """Summarize the data that arrived in the user's account during a period of time.

    The time range filters on when records were processed/synced into Fulcra,
    NOT on the records' own timestamps — e.g. last night's sleep records
    typically arrive this morning. Use this to find out what new data exists
    since a previous check, then query the changed types with the appropriate
    tools.

    Args:
        start_time: The start of the time range (inclusive). Must include tz (ISO8601).
        end_time: The end of the time range (exclusive). Must include tz (ISO8601).
    Returns:
        A JSON string with two keys:
        - "data_types": a map of each data type that had records processed
          during the range to the number of records processed. Most keys are
          catalog data type IDs (readable via get_records or
          get_metric_time_series); "apple_workout" refers to workouts
          (readable via get_workouts).
        - "file_changes": a list of uploaded files that were added, changed, or
          removed, with name, size, state, and upload/archive/delete timestamps.
          Changed files can be read with read_file — other agents may write
          files to pass data to this one.
    """
    fulcra = get_fulcra_object()
    updates = fulcra.data_updates(start_time, end_time)
    return f"Data updates from {start_time} to {end_time}: " + json.dumps(updates)


@tools_mcp.tool()
async def get_sleep(
    start_time: datetime,
    end_time: datetime,
    level: Literal["aggregate", "cycles", "stages"] = "cycles",
    cycle_gap: str | None = None,
    stages: list[int] | None = None,
    gap_stages: list[int] | None = None,
    clip_to_range: bool | None = True,
    merge_overlapping: bool | None = None,
    merge_contiguous: bool | None = None,
    mode: str | None = None,
    period: str | None = None,
    agg_functions: list[str] | None = None,
    time_zone: str | None = None,
) -> str:
    """Return the user's sleep data at a chosen level of detail.

    Pick the coarsest level that answers the question — results grow with detail:
    - "aggregate": stage totals per period (default 1 day), one row per period
      per stage. Best for multi-day questions ("how did I sleep this month").
    - "cycles": one row per sleep session.
    - "stages": every stage interval (the full hypnogram); single-night detail.

    Sleep spans midnight (starts day N, ends day N+1) — extend the time range
    accordingly. Stage integers: 0=In Bed, 1=Asleep/Unknown, 2=Awake, 3=Light,
    4=Deep, 5=REM. Result timestamps include time zones; translate them to the
    user's local time zone when known.

    Args:
        start_time: Range start (inclusive). Must include tz (ISO8601).
        end_time: Range end (exclusive). Must include tz (ISO8601).
        level: Level of detail (see above).
        cycle_gap: Minimum interval separating distinct cycles (e.g. "PT2H").
        stages: Stage integers to include (default: all).
        gap_stages: Stage integers treated as gaps between cycles.
        clip_to_range: Clip results to the requested range (default True).
        merge_overlapping: "stages" level only. Merge overlapping stages (default True).
        merge_contiguous: "stages" level only. Merge adjacent same-stage samples (default True).
        mode: "aggregate" level only. Assign cycles to periods by "start" or
              "end", or "split" intervals at period boundaries (default "end").
        period: "aggregate" level only. Period length, e.g. "1d", "1w" (default "1d").
        agg_functions: "aggregate" level only. E.g. "sum", "mean" (default ["sum"]).
        time_zone: "aggregate" level only. IANA tz for period boundaries
                   (default "UTC"; use the user's local tz so periods match their days).
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

    if level == "stages":
        if merge_overlapping is not None:
            kwargs["merge_overlapping"] = merge_overlapping
        if merge_contiguous is not None:
            kwargs["merge_contiguous"] = merge_contiguous
        query_func = fulcra.sleep_stages
    elif level == "aggregate":
        if mode is not None:
            kwargs["mode"] = mode
        if period is not None:
            kwargs["period"] = period
        if agg_functions is not None:
            kwargs["agg_functions"] = agg_functions
        if time_zone is not None:
            kwargs["tz"] = time_zone
        query_func = fulcra.sleep_agg
    else:
        query_func = fulcra.sleep_cycles

    sleep_df = query_func(
        start_time=start_time,
        end_time=end_time,
        **kwargs,
    )
    return f"Sleep {level} from {start_time} to {end_time}: " + sleep_df.to_json(
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


def _file_path(path: str, name: str = "") -> str:
    """Normalize a user-supplied file path to an absolute one, like the CLI does."""
    return str(PurePath("/", path, name))


def _slim_file(f: dict) -> dict:
    """Strip a file record down to the fields an MCP client needs."""
    keep = (
        "id",
        "name",
        "path",
        "size",
        "state",
        "scan_state",
        "created_at",
        "uploaded_at",
        "archived_at",
        "deleted_at",
        "restored_from_id",
        "source_name",
        "source_data_types",
    )
    return {k: f[k] for k in keep if f.get(k) not in (None, [], "")}


@tools_mcp.tool(annotations={"readOnlyHint": True})
async def list_files(path: str = "/", include_versions: bool = False) -> str:
    """List the files stored in the user's Fulcra account.

    Files can be used to pass data between agents: one agent writes a file with
    `write_file`, others notice the change via `get_data_updates` and read it
    with `read_file`.

    Args:
        path: A folder to list (default "/"), or a single file's full path.
        include_versions: When true, `path` must be a single file's full path;
            all stored versions of that file are returned, newest first. Version
            IDs can be passed to `restore_file`.
    Returns:
        A JSON string with "folders" and "files" lists, or a list of versions.
    """
    fulcra = get_fulcra_object()
    path = _file_path(path)
    if include_versions:
        try:
            versions = fulcra.resolve_filepath(path, all_versions=True)
        except Exception:
            return f"No file found at {path!r}. Use list_files without include_versions to browse folders."
        return f"Versions of {path}, newest first: " + json.dumps(
            [_slim_file(f) for f in versions]
        )
    listing = fulcra.list_files(path)
    result = {
        "folders": listing.get("folders") or [],
        "files": [_slim_file(f) for f in listing.get("files") or []],
    }
    if not result["folders"] and not result["files"]:
        try:
            result["files"] = [_slim_file(f) for f in fulcra.resolve_filepath(path)]
        except Exception:
            return f"No folder or file found at {path!r}."
    return f"Files at {path}: " + json.dumps(result)


@tools_mcp.tool(annotations={"readOnlyHint": True})
async def read_file(
    path: str,
    max_bytes: int = 100000,
    include_binary: bool = False,
) -> str:
    """Read the content of a file stored in the user's Fulcra account.

    Args:
        path: The full path of the file to read.
        max_bytes: Text content beyond this many bytes is truncated
            (default 100000). Pass a larger value only when the full content is
            truly needed; large files consume a lot of context.
        include_binary: Files that are not valid UTF-8 text are only returned
            when this is true, base64-encoded. Defaults to False.
    Returns:
        The file's text content (possibly truncated), or its base64-encoded
        content for binary files.
    """
    fulcra = get_fulcra_object()
    path = _file_path(path)
    try:
        file_record = fulcra.resolve_filepath(path)[0]
    except Exception:
        return f"No file found at {path!r}. Use list_files to see available files."
    data = fulcra.download_file(file_record["id"]).read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if not include_binary:
            return (
                f"{path} is a binary file ({len(data)} bytes). Pass "
                "include_binary=true to receive it base64-encoded; note that "
                "this can consume a large amount of context."
            )
        encoded = base64.b64encode(data).decode("ascii")
        if len(encoded) > max_bytes:
            return (
                f"{path} is a binary file ({len(data)} bytes, {len(encoded)} "
                f"base64 characters), exceeding max_bytes={max_bytes}. Binary "
                f"content is not truncated; pass max_bytes={len(encoded)} or "
                "more if you truly need it."
            )
        return f"Content of {path} (base64-encoded binary): {encoded}"
    if len(data) > max_bytes:
        truncated = data[:max_bytes].decode("utf-8", errors="replace")
        return (
            f"Content of {path} (truncated to the first {max_bytes} of "
            f"{len(data)} bytes; pass a larger max_bytes for more): {truncated}"
        )
    return f"Content of {path}: {text}"


@tools_mcp.tool(annotations={"destructiveHint": False})
async def write_file(path: str, content: str, content_type: str = "text/plain") -> str:
    """Write a text file to the user's Fulcra account.

    Writing to an existing path creates a new version; earlier versions are
    kept and can be restored with `restore_file`. Other agents can detect the
    change through `get_data_updates` (under "file_changes") and read it with
    `read_file`, so files are a good way to pass data between agents.

    Args:
        path: The full path to write to (e.g. "/agents/state.json").
        content: The text content to write.
        content_type: Optional MIME type. Defaults to "text/plain"; use e.g.
            "application/json" when writing JSON.
    Returns:
        A JSON string describing the written file.
    """
    fulcra = get_fulcra_object()
    path = _file_path(path)
    data = content.encode("utf-8")
    result = fulcra.upload_file(data, content_type, len(data), path)
    return f"Wrote {path}: " + json.dumps(_slim_file(result.get("file", result)))


@tools_mcp.tool(annotations={"destructiveHint": True})
async def delete_file(path: str) -> str:
    """Delete a file stored in the user's Fulcra account.

    This is a soft delete: earlier versions of the file are kept and can be
    restored with `restore_file` (find version IDs via list_files with
    include_versions=true).

    Args:
        path: The full path of the file to delete.
    """
    fulcra = get_fulcra_object()
    path = _file_path(path)
    try:
        file_record = fulcra.resolve_filepath(path)[0]
    except Exception:
        return f"No file found at {path!r}. Use list_files to see available files."
    fulcra.delete_file(file_record["id"])
    return f"Deleted {path} (version {file_record['id']})."


@tools_mcp.tool()
async def restore_file(version_id: str) -> str:
    """Restore a previous version of a file in the user's Fulcra account.

    Args:
        version_id: The UUID of the file version to restore, as returned by
            list_files with include_versions=true.
    Returns:
        A JSON string describing the restored file.
    """
    fulcra = get_fulcra_object()
    try:
        file_version = fulcra.get_file_by_version(version_id)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (
                f"No file version found with ID {version_id!r}. Use list_files "
                "with include_versions=true to find version IDs."
            )
        raise
    restored = fulcra.restore_file(file_version["id"])
    full_path = _file_path(file_version["path"], file_version["name"])
    return f"Restored {full_path}: " + json.dumps(_slim_file(restored))


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
