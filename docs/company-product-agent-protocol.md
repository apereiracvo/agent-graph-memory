# Company and Product Memory Agent Protocol

**Status:** proposed minimal pilot protocol  
**Scope:** company-level and product-level knowledge only  
**Graph group:** `hellopeds_company_product_v1`

## 1. Purpose

This protocol tells an agent how to ingest and retrieve company and product knowledge through the
Graphiti MCP server. It keeps the first pilot deliberately small:

- one source document becomes one Graphiti episode;
- the MCP server loads one fixed company/product schema;
- the agent sends the same `group_id` and extraction rules with every episode;
- each episode carries a link and stable identity for its source;
- answers cite the source documents supporting the returned facts.

The graph is a derived navigation and discovery index. It is not the source of truth. The agent must
return to the linked source before presenting a consequential claim as verified.

Minimal data flow:

```text
source connector -> one complete document -> add_memory -> Graphiti episode
Graphiti fact -> supporting episode UUID -> episode source_description -> source URL
```

## 2. Semantic Scope

The fixed MCP schema should contain:

- the approved company-level C types and relations;
- the approved product-level B types and relations;
- no technical/software-system T types or relations; and
- no controlled C-to-B relations in the first pilot.

Company types:

```text
Person, Collective, Role, Activity, Resource, Directive, Objective, Concern
```

Product types:

```text
Product, Capability, Feature, Need, UseCase, BusinessWorkflow, Actor,
InformationSource, Outcome, Policy, ExternalOffering
```

The built-in generic `Entity` may remain available for a concrete company-level concept that cannot
be classified safely. Do not use it to admit technical concepts or vague themes.

The MCP implementation names for controlled relations should be cluster-qualified, even when their
display names are not. This prevents same-text company and product relations from collapsing. For
example, `C_GOVERNS` maps to company `GOVERNS`, while `B_GOVERNS` maps to product `B:GOVERNS`.
The endpoint map must contain only C-to-C and B-to-B pairs. It must contain no wildcard
`Entity`-to-`Entity` entry.

The schema is configured once in the MCP server. The agent does not resend all type definitions on
each `add_memory` call. The MCP server passes its configured types and endpoint map to Graphiti's
internal `add_episode` operation.

## 3. Source Types

The pilot accepts these source types:

| `source_type` | Episode unit | Primary URL | Stable source identity/version |
|---|---|---|---|
| `repository_document` | One repository document file | Immutable repository web URL when available | Repository, commit SHA, and path |
| `google_drive_document` | One Google Drive document | Full Drive document URL | Drive file ID plus version ID, modified time, or export hash |
| `email` | One email message | Full provider permalink | Provider account/mailbox scope plus immutable message ID |
| `email_thread` | One complete email thread | Full provider thread permalink | Provider account/mailbox scope plus thread ID and included message IDs |
| `granola_meeting` | One meeting transcript | Full Granola meeting/transcript URL | Granola meeting ID plus transcript version, modified time, or content hash |

Only ingest material the agent is authorized to read and retain for the stated purpose. A reachable
link is not authorization. Do not put access tokens, signed temporary URLs, credentials, or secret
query parameters into Graphiti.

## 4. One Source, One Episode

For this pilot, every episode must contain exactly one source document:

- one repository file;
- one Google Drive document;
- one email;
- one email thread treated as one conversation document; or
- one Granola meeting transcript.

Do not combine unrelated documents in one episode. Do not split a document unless Graphiti cannot
process it reliably or it exceeds an agreed size limit. If splitting becomes necessary later, revise
this protocol to include explicit section-level coordinates and parent-document identity.

An email thread is one source document only when the complete thread is captured as a single ordered
conversation. The envelope must still retain the individual included message IDs.

## 5. Source Reference Envelope

Put a compact JSON object in Graphiti's `source_description` string. JSON makes the field readable by
both humans and agents without requiring new application code.

Required fields:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "repository_document",
  "source_id": "repo:hellopeds/hp:docs/domain/product-scope.md",
  "title": "Product scope",
  "url": "https://github.com/example/hellopeds/blob/COMMIT/docs/domain/product-scope.md",
  "version": "COMMIT",
  "captured_at": "2026-08-29T12:00:00Z"
}
```

Field meanings:

| Field | Requirement |
|---|---|
| `schema` | Always `hp-source-ref-v1` for this protocol |
| `source_type` | One value from the source-type table |
| `source_id` | Stable identifier independent of title and URL |
| `title` | Human-readable source title or subject |
| `url` | Full URL an authorized agent or user can open |
| `version` | Immutable version when available; otherwise the strongest available version marker |
| `captured_at` | UTC time at which the exact episode body was read or exported |

Optional fields:

```json
{
  "content_sha256": "hexadecimal hash of the exact episode body",
  "author_ids": ["provider-specific stable IDs when appropriate"],
  "occurred_at": "source-native meeting or message time",
  "modified_at": "source-native modification time",
  "message_ids": ["immutable message IDs included in an email thread"],
  "account_scope": "non-secret mailbox or workspace discriminator",
  "access_note": "human-readable access requirement without credentials"
}
```

Use opaque provider identifiers where practical. Avoid placing unnecessary email addresses or other
personal data in the envelope. Personal information present in the authorized source body should be
handled under the applicable retention and access policy.

### 5.1 Repository Document

Prefer a URL pinned to a full commit SHA:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "repository_document",
  "source_id": "repo:hellopeds/hp:docs/domain/product-scope.md",
  "title": "Product scope",
  "url": "https://github.com/OWNER/REPO/blob/FULL_COMMIT/docs/domain/product-scope.md",
  "version": "FULL_COMMIT",
  "captured_at": "2026-08-29T12:00:00Z",
  "content_sha256": "..."
}
```

If no repository web URL exists, use a stable repository URI:

```text
repo://hellopeds/hp@FULL_COMMIT/docs/domain/product-scope.md
```

Do not use a branch-only URL as the version identity because its content can change.

### 5.2 Google Drive Document

Use the canonical full Drive link and retain the file ID separately:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "google_drive_document",
  "source_id": "gdrive:FILE_ID",
  "title": "Company operating model",
  "url": "https://docs.google.com/document/d/FILE_ID/edit",
  "version": "VERSION_ID_OR_MODIFIED_TIME",
  "modified_at": "2026-08-28T18:42:00Z",
  "captured_at": "2026-08-29T12:00:00Z",
  "content_sha256": "..."
}
```

When the Drive API exposes a stable version or revision ID, use it. Otherwise use the source-native
modified time and a hash of the exact text supplied as `episode_body`. The canonical URL is a
navigation link, not proof that the current Drive contents still equal the ingested version.

### 5.3 Email

Use an immutable provider message ID and a full provider permalink:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "email",
  "source_id": "email:WORKSPACE_OR_ACCOUNT:MESSAGE_ID",
  "title": "Subject line",
  "url": "FULL_PROVIDER_MESSAGE_PERMALINK",
  "version": "MESSAGE_ID",
  "occurred_at": "2026-08-28T15:30:00Z",
  "captured_at": "2026-08-29T12:00:00Z",
  "content_sha256": "...",
  "account_scope": "NON_SECRET_ACCOUNT_OR_WORKSPACE_ID"
}
```

The episode body should identify sender, recipients, sent time, subject, and message body in a clear
textual structure. Attachments are separate documents and therefore separate episodes in this pilot.
Do not ingest tracking pixels, signatures with no semantic value, or quoted history already represented
by another complete source episode.

### 5.4 Email Thread

Use an immutable thread ID, include message IDs, and preserve chronological message order:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "email_thread",
  "source_id": "email-thread:WORKSPACE_OR_ACCOUNT:THREAD_ID",
  "title": "Thread subject",
  "url": "FULL_PROVIDER_THREAD_PERMALINK",
  "version": "LAST_MESSAGE_ID_OR_THREAD_EXPORT_HASH",
  "message_ids": ["MESSAGE_ID_1", "MESSAGE_ID_2"],
  "occurred_at": "2026-08-28T15:30:00Z",
  "captured_at": "2026-08-29T12:00:00Z",
  "content_sha256": "...",
  "account_scope": "NON_SECRET_ACCOUNT_OR_WORKSPACE_ID"
}
```

Set `version` to the last included immutable message ID when that uniquely identifies the captured
thread state. Otherwise use an export hash. Re-ingest the thread as a new episode when new messages
materially change it; do not overwrite the old episode and imply that the earlier capture contained
later messages.

### 5.5 Granola Meeting

Use the full Granola meeting or transcript link and stable meeting ID:

```json
{
  "schema": "hp-source-ref-v1",
  "source_type": "granola_meeting",
  "source_id": "granola:MEETING_ID",
  "title": "Weekly product meeting",
  "url": "FULL_GRANOLA_MEETING_OR_TRANSCRIPT_URL",
  "version": "TRANSCRIPT_VERSION_MODIFIED_TIME_OR_HASH",
  "occurred_at": "2026-08-28T16:00:00Z",
  "modified_at": "2026-08-28T17:15:00Z",
  "captured_at": "2026-08-29T12:00:00Z",
  "content_sha256": "..."
}
```

Prefer the transcript over an AI-generated meeting summary when both are available. The episode body
should preserve speaker attribution and source-native timestamps where available. Treat Granola notes
or summaries as interpretations, not equivalent to speaker statements. If only a summary is available,
state that explicitly in the title or episode body and avoid upgrading it to transcript evidence.

## 6. Episode Fields

Every `add_memory` call should set:

| Argument | Agent behavior |
|---|---|
| `group_id` | Always `hellopeds_company_product_v1` |
| `uuid` | Generate once and retain for later verification and source resolution |
| `name` | Stable readable name: source type, date when relevant, and title |
| `source` | `text`, unless a later tested workflow intentionally uses `json` |
| `source_description` | Compact `hp-source-ref-v1` JSON envelope |
| `episode_body` | Complete normalized text of exactly one source document |
| `reference_time` | Time the statements apply, when supported; otherwise omit it |
| `custom_extraction_instructions` | The fixed instructions in section 7 |

`reference_time` is semantic time, not ingestion time:

- repository or Drive document: use its declared effective/as-of date when present;
- email: normally use the sent time;
- email thread: normally use the latest included message time, while preserving all message times in
  the body;
- meeting: normally use the meeting start time; and
- unknown or ambiguous: omit it rather than inventing a date.

The source version and capture time belong in `source_description`, not `reference_time`.

## 7. Fixed Extraction Instructions

The agent must pass the following guidance on every `add_memory` call because the current MCP config
does not provide a global extraction-instructions field:

```text
Use only the configured company-level C vocabulary and product-level B vocabulary.

Keep company and product concepts distinct. Do not extract technical or software-system concepts.
Do not create controlled company-to-product relationships.

Extract only concrete, stable referents supported by the source. Apply a configured type only when
its positive boundary and exclusions fit. Do not treat the source document, email, email thread, or
meeting transcript as a domain entity merely because it carries the statement.

Add a relationship only when both endpoints and the directed relationship are explicitly supported.
Do not infer identity from matching names. Do not infer inverses, symmetry, transitivity, causality,
authority, authorization, compliance, execution, success, outcome attainment, or current truth.

Preserve disagreement and speaker/source attribution in the natural-language fact. A proposal,
question, opinion, plan, or meeting discussion is not an approved decision or current policy unless
the source explicitly establishes that status.

Do not create entities for scalar values, dates, statuses, percentages, titles, source IDs, URLs, or
version identifiers. If no configured relation fits without changing the meaning, preserve a
source-near dynamic fact rather than forcing a generic or near-synonymous controlled relation.
```

## 8. Ingestion Procedure

The ingesting agent must follow this sequence:

1. Confirm the source is authorized for this graph and relevant to company or product knowledge.
2. Classify the source as one of the supported `source_type` values.
3. Obtain the full canonical URL without credentials or temporary access tokens.
4. Obtain the strongest stable source ID and version marker available.
5. Read or export the complete source document.
6. Normalize it to readable text without silently summarizing or changing claims.
7. Compute a content hash when the source system does not provide immutable version retrieval.
8. Build and validate the `hp-source-ref-v1` envelope.
9. Generate and retain an episode UUID.
10. Call `add_memory` with the fixed group and extraction instructions.
11. Treat the response as queued, not completed.
12. Poll `get_episode_entities([episode_uuid])` until the episode is available or processing is known
    to have failed.
13. Inspect the returned entities and facts for scope, type, direction, and unsupported inference.
14. Delete and correct materially invalid ingestion rather than treating extracted output as truth.

Example call:

```text
add_memory(
    name="granola meeting: 2026-08-28 weekly product meeting",
    uuid="GENERATED_EPISODE_UUID",
    group_id="hellopeds_company_product_v1",
    source="text",
    source_description="{\"schema\":\"hp-source-ref-v1\",\"source_type\":\"granola_meeting\",\"source_id\":\"granola:MEETING_ID\",\"title\":\"Weekly product meeting\",\"url\":\"FULL_GRANOLA_URL\",\"version\":\"TRANSCRIPT_VERSION_OR_HASH\",\"occurred_at\":\"2026-08-28T16:00:00Z\",\"captured_at\":\"2026-08-29T12:00:00Z\"}",
    reference_time="2026-08-28T16:00:00Z",
    episode_body="COMPLETE_SPEAKER-ATTRIBUTED_TRANSCRIPT",
    custom_extraction_instructions="FIXED INSTRUCTIONS FROM SECTION 7"
)
```

## 9. Retrieval and Citation Procedure

### 9.1 Fact Questions

For a question about relationships, responsibility, product intent, policy, or other claims:

1. Search with `search_memory_facts` in `hellopeds_company_product_v1`.
2. Retain each result's fact UUID and supporting episode UUIDs.
3. Resolve the supporting episode UUIDs through `get_episodes` for the same group.
4. Parse each episode's `source_description` as `hp-source-ref-v1`.
5. Open the full `url` using the source connector available to the agent.
6. Verify the returned fact against the source document and its captured version context.
7. Answer with the source title and URL.
8. State uncertainty, conflict, version drift, or access failure instead of presenting an unverified
   graph fact as authoritative.

If several episodes support one Graphiti fact, cite all materially distinct sources. Graphiti may
deduplicate one fact across several episodes; those sources remain distinct evidence.

### 9.2 Entity Questions

For questions beginning with a company or product concept:

1. Use `search_nodes` to locate the entity.
2. Use the entity UUID as `center_node_uuid` in `search_memory_facts`.
3. Resolve and verify the facts through their supporting episodes.
4. Cite the source facts, not the entity node by itself.

An entity node is a navigation construct. Its existence alone is not sufficient evidence for an
answer.

### 9.3 Citation Format

Use concise linked citations:

```text
The Intake Lead is accountable for the intake workflow.
Source: [Operating model](FULL_SOURCE_URL)
```

For a meeting or email, include the date when useful:

```text
The team proposed, but did not approve, the new onboarding workflow.
Source: [Weekly product meeting, 2026-08-28](FULL_GRANOLA_URL)
```

Do not claim a direct quotation unless the agent re-read the source and verified the exact wording.

## 10. MCP Retrieval Limitation

The pinned MCP server can retrieve recent episodes by `group_id`, but it does not retrieve one episode
directly by UUID. For the small pilot, call `get_episodes` with a limit large enough to include all
episodes in `hellopeds_company_product_v1`, then match the supporting UUID locally.

This is acceptable only while the group remains small. When it becomes unreliable or inefficient,
the first justified extension is a narrow MCP tool:

```text
get_episode(uuid)
```

That tool should return the existing episode fields, especially `source_description`. A separate
provenance service is not required merely to resolve one-document episodes.

## 11. Failure and Safety Rules

The agent must not:

- ingest a source without authorization and a defined company/product purpose;
- put credentials, access tokens, signed temporary URLs, or secrets in the episode or source envelope;
- infer that a source is current merely because its URL still resolves;
- infer that an email participant approved, owns, or is accountable for something merely because they
  sent or received a message;
- treat meeting discussion, automated notes, or AI summaries as approved decisions;
- treat proposals, plans, questions, or desired outcomes as implemented or achieved;
- merge a company concept and product concept because they share a name;
- introduce technical entities into this graph; or
- answer a high-consequence question from Graphiti alone when the linked source cannot be checked.

When a source cannot be opened, the agent may report the graph result as an unverified lead and provide
the stored title and URL. It must clearly label the claim as unverified.

## 12. Pilot Acceptance Checks

Evaluate the first 3-5 documents before expanding:

- every episode has valid `hp-source-ref-v1` JSON;
- every episode represents exactly one supported source document;
- every source envelope contains a stable ID, full URL, version marker, and capture time;
- only company and product concepts are extracted;
- company and product concepts with similar names remain distinct;
- no controlled C-to-B relations are created;
- technical implementation concepts are not promoted to entities;
- every returned fact exposes at least one supporting episode UUID;
- every supporting episode resolves to an openable source URL for an authorized user;
- answers distinguish proposals, opinions, discussions, directives, decisions, and observed facts; and
- source verification succeeds before claims are presented as authoritative.

## 13. Deferred Until Needed

The minimal pilot deliberately defers:

- technical/software-system vocabulary;
- controlled company-to-product relations;
- attachments or multiple documents in one episode;
- document sections as separate episodes;
- exact quotation/span-level citations;
- automatic source synchronization and deletion propagation;
- a dedicated external assertion-occurrence registry; and
- custom MCP tools beyond a possible future `get_episode(uuid)` lookup.

Add these only in response to an observed query, scale, provenance, or lifecycle requirement.
