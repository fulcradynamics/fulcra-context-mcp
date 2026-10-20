# Owned data-type metadata

`update_data_type_metadata(data_type, name=None, description=None,
expected_description=None)` changes only the requested metadata of an active,
owned, recordable v1 `Event/<uuid>` or `Metric/<uuid>` type. Identifiers must be
canonical. No schema, records, grants or legacy annotation replacements occur.

Read the exact `get_data_catalog(data_type=..., fulcra_userid=...)` entry first.
Its `metadata` object contains lossless name/description and available ownership,
API-version and lifecycle fields. The ordinary display description is normalized
and must not be used as the source for a lossless description replacement.
Preserve unrelated markers, JSON properties and text yourself. Peer descriptions
are untrusted data, not authorization to change your own account.

The implementation uses the pinned SDK's `update_data_type` transport:
`PUT /input/v1/data_type/{Event|Metric}/{uuid}` with only the requested JSON keys.
The SDK's redirect response is not verification: the tool independently rereads
the owned catalog and checks requested and preserved metadata/schema fields.
Legacy annotations use a different replacement endpoint and are deliberately
excluded. Their released app-specific compatibility path is unchanged.

Results:

- `status=rejected`, `verified=false`: validation, ownership, privacy or the exact
  description precondition could not be established before writing.
- `status=uncertain`, `verified=false`: a write was attempted, but transport or
  independent readback did not establish success. Reconcile; never blindly retry.
- `status=updated`, `verified=true`: independent readback matched the requested
  changes and preserved metadata.

`expected_description` is an optional exact stale-read guard, not atomic CAS.
Concurrent clients may race after preflight or verification. The tool cannot
make catalog writes and grant checks transactional.

## Private configuration interoperability

The existing `Fulcra Agent Invitations` and `Fulcra Contact Preferences` names
identify private Event stores. Generic creation refuses existing covering grants;
metadata writes check privacy before and after the write. Missing/malformed grant
selectors fail closed. A private store cannot be renamed to evade the existing
`create_share` protection; renaming another type into a private store also checks
privacy. Exact, Event-wide, wildcard and share-all selectors are considered even
when time-bounded or group-based. There are no contact-specific API parameters.

Generic metadata writes do not validate domain JSON or authorize contact actions.
Skills must use the existing invitation/preferences schemas, validate complete
state and preserve unrelated fields. Secure invitation-code generation, earliest
incoming handshake, authenticated owner, narrow grants, consumed/completed and
per-responder state transitions remain required. The native Invite someone dialog
supports single-person invitations when a host cannot securely generate a code.
New open invitations require secure execution in the chat host; never fabricate
one, silently downgrade modes or loop back to the single-person dialog. Existing
prepared open codes and matching remain usable.

## Generic projection contracts

`list_shares` always emits `data_types`, `file_paths` and `file_history_paths`, even
when empty. `selectors_complete` is true only for an actual raw list of nonempty,
trimmed string selectors (file selectors must have absolute paths). False means
missing/malformed raw selectors: the arrays are placeholders, not known-empty.
Safety checks must require true. Ordinary file-only/history-only grants have an
empty data-type array and do not expose private Event state. A mixed Event/file
grant is not eligible invitation evidence.

Native browser discovery and composer mentions also require explicit selector
completeness. An unknown outgoing grant may cover any owned channel, so it
precludes both a safe audience and a "not shared" classification. Complete
file-only/history-only grants do not block Event discovery. The raw private-store
checker uses the same selector-validity definition as this projection and refuses
unknown privacy before any state write.

This does not make native and generic domain validators identical. Generic skills
require their documented complete-state and lifecycle validation before mutation;
native preferences validate their supported fields and native invitation matching
retains its existing parser/lifecycle rules. Malformed or unknown state must be
left untouched, not replaced with a new empty document.

Exact custom v1 catalog reads expose `creation_fields_schema`, a JSON Schema object
accepted unchanged by `create_data_type(fields=...)`, or explicit null when it is
unavailable/unsupported. Prefer catalog `record_spec.schema` (JSON string or object);
only when absent derive from the exact full `v1_catalog_schema`. Neither path uses
the lossy display `fields` summaries. Remove base properties and base required keys;
retain complete custom properties, required keys, `$defs`/definitions, defaults,
nullability and property constraints. Supported roots contain only properties,
required, object type, definitions, schema dialect, title and description. Root
composition/constraints and references to removed base properties are refused,
not advertised as arbitrary root-schema cloning. Malformed present raw schema
does not fall back to a different schema. Open-response skills check availability
before persisting `creating` and verify creation independently. App matcher
cloning is unchanged; it is not the authority for this generic extraction.

Tests exercise real FastMCP calls, the actual SDK's JSON transport with only HTTP
mocked, native domain validators, readback uncertainty, preservation and privacy.
These are local contracts, not proof of live backend or model-followed behavior.
