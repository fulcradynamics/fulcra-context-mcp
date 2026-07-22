# AGENTS.md - Context by Fulcra

> Context by Fulcra - bridging the gap between agents and humans.

## About

[Context by Fulcra](https://fulcradynamics.com/) is a personal data platform that provides humans a place to collect and store real-world personal data - from wearables, calendars, location, medical devices, and more. Hundreds of data sources and types supported.
In addition, there are facilities to help users record new free-form data:  their own subjective feelings (to record your mood, sleep, etc.) and track progress toward a goal. 

Data is primarily collected through the human's phone; the human installs [Context by Fulcra](https://apps.apple.com/us/app/context-by-fulcra-health-hub/id1633037434) and lets the app sync their data to their account.


### Interactive Access to the User's Data
The human user gets to investigate their data interactively using beautiful mobile and [web apps](https://context.fulcradynamics.com/).

### Agentic/Programmatic Access To the User's Data
* Fully supported [OAuth2 REST API](https://fulcradynamics.github.io/developer-docs/):
    * [OpenAPI spec](https://api.fulcradynamics.com/openapi.json)
* [Python client library](https://fulcradynamics.github.io/fulcra-api-python/) (`pip install fulcra-api`): For an easy way to use the client library. Handles authentication for you. It also includes the `fulcra` CLI, which gives command-line access to the full platform — data queries, the data type catalog, tags, user-defined data types, and file storage. Sub-commands emit JSON lines for piping into tools like `jq`; run `fulcra --help` for the command list.
* [MCP Server Docs](https://fulcradynamics.github.io/developer-docs/mcp-server/): A guide on how to use the MCP server.
* [MCP server](https://mcp.fulcradynamics.com): The endpoint to the public MCP server. The server uses Streamable HTTP transport with OAuth2 authorization. Context users can use this server with their own account to securely access their data.
* [MCP server source code](https://github.com/fulcradynamics/fulcra-context-mcp): The open-source repository for the MCP server. Useful for inspecting available tools, running locally, or contributing.

### For Agents and LLMs: Authorization Tips

#### Code-first agents

If you can run shell commands, try the `fulcra` CLI first; it ships as part of the `fulcra-api` client library (`pip install fulcra-api`). Authenticate once with:

```
fulcra auth login
```

This uses the OAuth2 Device Authorization Flow: it prints a URL for the operator (the user) to open in a browser, polls until they approve, and persists credentials (including a refresh token) at `~/.config/fulcra/credentials.json`, so subsequent commands need no re-authentication.

If you can't keep a process alive while the user completes the browser flow, use the split, non-interactive variant:

```
fulcra auth login --get-auth-url          # prints the auth URL and a device code; send the URL to the user
fulcra auth login --device-code <CODE>    # run after the user finishes the browser flow
```

To make direct REST API calls, `fulcra auth print-access-token` prints a bearer token, e.g.:

```
curl --oauth2-bearer "$(fulcra auth print-access-token)" 'https://api.fulcradynamics.com/user/v1alpha1/info'
```

If you're writing Python code, the same flow is available on the `fulcra-api` module. When calling `.authorize()`, the output will include a URL that you can send to the operator; the call polls while the user completes it in a browser. If the call times out, call `authorize()` again to get a new URL.

```
>>> from fulcra_api.core import FulcraAPI
>>> fulcra = FulcraAPI()
>>> fulcra.authorize()

            Use your browser to log in to Fulcra.  If the tab does not open
            automatically, visit this URL to authenticate: https://fulcra.us.auth0.com/activate?user_code=DBNV-DBQV
```

#### Text-first agents

For agents without the ability to run shell commands or Python code, use the [MCP server](https://mcp.fulcradynamics.com). This server includes tools that can access the same data sources that the API can.

The user can either use the public MCP server instance at `https://mcp.fulcradynamics.com`, or run it locally. It is published as the `fulcra-context-mcp` PyPI module.

You can run it locally (stdio transport) with `uvx fulcra-context-mcp@latest`. See the [PyPI page](https://pypi.org/project/fulcra-context-mcp/) for more docs.

#### MCP Client Configuration Examples

Remote connection using proxy (for clients like Claude for Desktop that only support stdio):
```json
{
    "mcpServers": {
        "fulcra_context": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "https://mcp.fulcradynamics.com/"
            ]
        }
    }
}
```

Local connection using `uvx`:
```json
{
    "mcpServers": {
        "fulcra_context": {
            "command": "uvx",
            "args": [
                "fulcra-context-mcp@latest"
            ]
        }
    }
}
```

## MCP tools and tips

There are MCP tools available to both get general information about the user and specific data. Start with the former, with calls like `get_user_info`, `get_data_catalog`, and `annotations_catalog`, to get a sense of what the user has chosen to record. Then use the other tools (e.g. `get_time_series`, `get_records`, `get_sleep`, etc.) to get the data for specific time range(s).

`get_data_catalog` returns every available data type grouped by the tools that can read it — only use a data type with the tools named in its group. `get_records` retrieves raw records for any data type in the catalog (including user-defined ones); `get_time_series` computes per-interval values and only supports the types listed under it.

All time parameters must include time zones (ISO 8601 format). Always translate result timestamps to the user's local time zone when known.

### Measuring tool context cost (for contributors)

Tool definitions (descriptions + schemas) are loaded into every MCP client
conversation, so their size matters. To measure the current cost per tool and
in total, run this from the repo root:

```sh
uv run python scripts/measure_tools.py
```

Pass another checkout's path as an argument to compare versions (e.g. `uv run
python scripts/measure_tools.py ../main-checkout`). Treat it as a regression
check when adding or editing tools: a change that adds hundreds of tokens of
definitions should be earning them.

## Available Data

### Health & Biometrics
Sleep stages, sleep duration, sleep efficiency, HRV (heart rate variability), heart rate, resting heart rate, blood oxygen (SpO2), respiratory rate, wrist temperature, steps, calories burned (active and basal), workouts, body composition (weight, body fat), atrial fibrillation burden. Sources include Apple Health, Garmin, Oura, Whoop, and other connected devices.

### Glucose & Nutrition
Continuous glucose monitor (CGM) readings from Dexcom and Libre, meal logs, macronutrient tracking, calorie intake, hydration data. Enables correlation of nutrition with biometric outcomes.

### Location & Calendar
Real-time and historical location data, plus calendar events and meeting schedules synced from the user's device calendars (Apple Calendar, including any subscribed Google or other calendars). The location tools return a fused interpretation of where the user was at a given time, combining whatever underlying data sources are available rather than exposing raw per-source samples.

### Annotations & Custom Events
User-logged medications, supplements, mood entries, device usage, and custom events. These can be discovered, classified, and correlated with biometric streams over time. Users (and agents, via the CLI's `data-type` and `tag` commands) can define new data types to track.

### Files
Users can upload arbitrary files to their account for storage alongside their data. The CLI's `file` sub-commands support list, stat, upload, download, delete, and version restore.

### Time Series Metrics

Example metrics from the catalog: `StepCount`, `HeartRate`, `HeartRateVariabilitySDNN`, `SleepStage`, `ActiveCaloriesBurned`, `BasalCaloriesBurned`, `RespiratoryRate`, `OxygenSaturation`, `BodyTemperature`, `AFibBurden`, and many more.

## Best Practices for Agents

- **Use appropriate sample rates.** When querying time series data, choose a `sample_rate` that balances resolution with performance. For daily overviews, 3600 seconds (hourly) works well. For detailed analysis, 60-300 seconds.
- **Sleep spans midnight.** Sleep cycles typically start on day N and end on day N+1. When querying sleep data, account for this by extending your date range.
- **Correlate across domains.** The real power of Context is combining data streams - sleep quality with nutrition, HRV with training load, location with calendar events. Look for patterns across domains.

### Example: Querying Data with the CLI

```sh
# Discover available data types (supports --name, --category, and --data-type filters)
fulcra catalog --name heart

# Get heart rate data for a day (hourly resolution)
fulcra metric-time-series HeartRate "2025-01-01T00:00:00-08:00" "2025-01-02T00:00:00-08:00" --sample-rate 3600

# Raw records for any catalog data type; time ranges can also be relative
fulcra get-records StepCount "1 day"
```

The `related_cli_commands` property on each `fulcra catalog` entry lists the sub-commands that work with that data type.

### Example: Querying Data with the Python Client

```python
from fulcra_api.core import FulcraAPI

fulcra = FulcraAPI()
fulcra.authorize()

# Discover available data types (metrics, events, annotations)
catalog = fulcra.v1_catalog()

# Get heart rate data for a day (hourly resolution)
data = fulcra.metric_time_series(
    metric="HeartRate",
    start_time="2025-01-01T00:00:00-08:00",
    end_time="2025-01-02T00:00:00-08:00",
    sample_rate=3600
)
```

### Jupyter Notebook Demos

Ready-to-run demo notebooks are available at the [Fulcra demos repository](https://github.com/fulcradynamics/demos). These notebooks walk through common use cases like querying health metrics, analyzing sleep, and correlating data across domains. They can also be opened directly in [Google Colab](https://colab.research.google.com/) for one-click, zero-install demos.

## Support

- **Email:** support@fulcradynamics.com
- **Discord:** [Context Social Discord](https://discord.gg/fulcra)
- **GitHub:** [github.com/fulcradynamics](https://github.com/fulcradynamics)
- **Live Web Chat:** Available on fulcradynamics.com

## Official domains
* fulcradynamics.com
* context.fulcradynamics.com
* mcp.fulcradynamics.com
* fulcra.ai
