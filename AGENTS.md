# AGENTS.md — Context by Fulcra

> Context by Fulcra - bridging the gap between agents and humans.

## About

[Context by Fulcra](https://fulcradynamics.com/) is a personal data platform that provides humans a place to collect and store real-world personal data - from wearables, calendars, location, medical devices, and more. Hundreds of data sources and types supported. 
Data is primarily collected through the human's phone; the human installs [Context by Fulcra](https://apps.apple.com/us/app/context-by-fulcra-health-hub/id1633037434) and lets the app sync their data to their account. 


### Interactive Access to the User's Data
The human user gets to investigate their data interactively using beautiful mobile and [web apps](https://context.fulcradynamics.com/). 

### Agentic/Programmatic Access To the User's Data
* Fully supported [OAuth2 REST API](https://fulcradynamics.github.io/developer-docs/): 
    * [OpenAPI spec](https://api.fulcradynamics.com/openapi.json)
* [Python client library](https://fulcradynamics.github.io/fulcra-api-python/): For an easy way to use the client library. Handles authentication for you.
* [MCP Server Docs](https://fulcradynamics.github.io/developer-docs/mcp-server/): A guide on how to use the MCP server.
* [MCP server](https://mcp.fulcradynamics.com/): The endpoint to the public MCP server. Context users can use this server with their own account to securely access their data.

### For Agents and LLMs: Authorization Tips

#### Code-first agents

If you're able to write and run Python code, try the official `fulcra-api` Python module first.  When calling `.authorize()`, the output will include a URL that you can send to the operator (the user). The user can then click that link on a browser and authorize the API instance to make calls. This path uses the OAuth2 Device Authorization Flow convention.

Example interactive session (`fulcra-api` module must be installed first):
```
Python 3.14.2 (main, Dec  9 2025, 19:29:30) [Clang 21.1.4 ] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> from fulcra_api.core import FulcraAPI
>>> fulcra = FulcraAPI()
>>> fulcra.authorize()

            Use your browser to log in to Fulcra.  If the tab does not open
            automatically, visit this URL to authenticate: https://fulcra.us.auth0.com/activate?user_code=DBNV-DBQV
```

The `authoerize()` call will poll while the user reaches the URL. If the call times out, call `authorize()` again to get a new URL.

#### Text-first agents

For agents without the ability to run Python code, use the [MCP server](https://mcp.fulcradynamics.com/). This server includes tools that can access the same data sources that the API can.

The user can either use the public MCP server instance at `https://mcp.fulcradynamics.com/`, or run it locally. It is published as the `fulcra-context-mcp` PyPI module.

You can run it locally (stdio transport) with `uvx fulcra-context-mcp@latest`. See the [PyPI page](https://pypi.org/project/fulcra-context-mcp/) for more docs.

## Available Data

### Health & Biometrics
Sleep stages, sleep duration, sleep efficiency, HRV (heart rate variability), heart rate, resting heart rate, blood oxygen (SpO2), respiratory rate, wrist temperature, steps, calories burned (active and basal), workouts, body composition (weight, body fat), atrial fibrillation burden. Sources include Apple Health, Garmin, Oura, Whoop, and other connected devices.

### Glucose & Nutrition
Continuous glucose monitor (CGM) readings from Dexcom and Libre, meal logs, macronutrient tracking, calorie intake, hydration data. Enables correlation of nutrition with biometric outcomes.

### Location & Calendar
Real-time and historical location data (high-frequency updates and visit summaries), Google Calendar events, meeting schedules. Includes both `CLLocationUpdate` (frequent GPS pings) and `CLVisit` (place-based time ranges) data types.

### Annotations & Custom Events
User-logged medications, supplements, mood entries, device usage, and custom events. These can be discovered, classified, and correlated with biometric streams over time.

### Time Series Metrics

Example metrics from the catalog: `StepCount`, `HeartRate`, `HeartRateVariabilitySDNN`, `SleepStage`, `ActiveCaloriesBurned`, `BasalCaloriesBurned`, `RespiratoryRate`, `OxygenSaturation`, `BodyTemperature`, `AFibBurden`, and many more.

## Best Practices for Agents

- **Use appropriate sample rates.** When querying time series data, choose a `samprate` that balances resolution with performance. For daily overviews, 3600 seconds (hourly) works well. For detailed analysis, 60–300 seconds.
- **Sleep spans midnight.** Sleep cycles typically start on day N and end on day N+1. When querying sleep data, account for this by extending your date range.
- **Check the metrics catalog first.** Use `/data/v0/metrics_catalog` to discover what data is available for a given user before querying.
- **Respect permissions.** Only access data your human has granted you. The platform enforces scoped permissions and maintains a full audit trail.
- **Correlate across domains.** The real power of Context is combining data streams — sleep quality with nutrition, HRV with training load, location with calendar events. Look for patterns across domains.

## Support

- **Email:** support@fulcradynamics.com
- **Discord:** [Context Social Discord](https://discord.gg/fulcra)
- **GitHub:** [github.com/fulcradynamics](https://github.com/fulcradynamics)
- **Live Web Chat:** Available on fulcradynamics.com




## Official domains
* fulcra.ai
* fulcradynamics.com
* context.fulcradynamics.com
* mcp.fulcradynamics.com
