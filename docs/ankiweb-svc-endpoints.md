# Anki Desktop ↔ AnkiWeb `/svc/` Endpoints (Protobuf)

Last checked: commit `70c8ce4cb369c163d55c67b3b49424ca9b854bc5` of `ankitects/anki`.

These notes summarize the **protobuf-based** AnkiWeb endpoints the desktop client calls under `https://ankiweb.net/svc/`, as visible in the OSS codebase. Use this to guide any tooling or demo you build. Respect AnkiWeb’s ToS and the repo’s AGPLv3 license.

---

## Scope

- **Protobuf endpoints under `/svc/`:** Two calls under `https://ankiweb.net/svc/`:
  - `desktop/addon-info`
  - `desktop/check-for-update`
- **Transport:** HTTP POST, protobuf-encoded request/response, 60s timeout.
- **Client implementation:** `rslib/src/backend/ankiweb.rs` (Rust) calls `service_url("desktop/...")` and POSTs protobuf bytes.
- **Schemas:** `proto/anki/ankiweb.proto` defines request/response messages.

Other AnkiWeb URLs are referenced by the desktop app (eg, shared deck pages), but they are not `/svc/` protobuf APIs. Sync uses a different endpoint (`https://sync.ankiweb.net/`) and protocol (implemented primarily under `rslib/src/sync/`).

---

## Base URL

```

https://ankiweb.net/svc/{service}

```

`service` values currently used: `desktop/addon-info`, `desktop/check-for-update`.

---

## Protobuf schemas (from `proto/anki/ankiweb.proto`)

### `GetAddonInfo`

- **Request**
  - `client_version: uint32` — desktop client version number.
  - `addon_ids: repeated uint32` — up to 25 add-on IDs per request.
- **Response**
  - `info: repeated AddonInfo`
    - `id: uint32`
    - `modified: int64` — timestamp (seconds since epoch).
    - `min_version: uint32`
    - `max_version: uint32`

### `CheckForUpdate`

- **Request**
  - `version: uint32` — client version.
  - `buildhash: string` — build hash of the client.
  - `os: string` — OS identifier.
  - `install_id: int64` — client install id.
  - `last_message_id: uint32` — last message seen by client.
- **Response**
  - `new_version: optional string` — if an update is available.
  - `current_time: int64` — server time (seconds).
  - `message: optional string` — message to display.
  - `last_message_id: uint32` — latest message id.

---

## How the desktop calls these

- The Rust backend posts protobuf bytes with a 60s timeout and checks HTTP status before decoding.
- Uses a shared `reqwest` client from the backend (`Backend::web_client()`), not shown here; important only if you need headers/UA (none special besides defaults).
- No auth is shown for these two endpoints in the OSS code.

---

## Example call flow (conceptual)

1. Build protobufs from `proto/anki/ankiweb.proto` in your chosen language.
2. POST to `https://ankiweb.net/svc/desktop/addon-info` with binary body = encoded `GetAddonInfoRequest`.
3. Set `Content-Type: application/octet-stream` (the official client doesn’t set a custom content-type, but this is safe).
4. Decode response bytes as `GetAddonInfoResponse`.

---

## Pseudocode snippets

### Fetch add-on info

```python
# Requires generated protobuf classes from proto/anki/ankiweb.proto.
# In Anki's build, these land under the `anki.*_pb2` modules (generated), and
# may not exist as checked-in `.py` files in the repo.
import requests
from anki.ankiweb_pb2 import GetAddonInfoRequest, GetAddonInfoResponse

req = GetAddonInfoRequest(client_version=30, addon_ids=[3918629684, 1234567890])
resp = requests.post(
    "https://ankiweb.net/svc/desktop/addon-info",
    data=req.SerializeToString(),
    timeout=60,
)
resp.raise_for_status()
out = GetAddonInfoResponse()
out.ParseFromString(resp.content)
print(out)
```

### Check for update

```python
import platform, uuid, requests
from anki.ankiweb_pb2 import CheckForUpdateRequest, CheckForUpdateResponse

req = CheckForUpdateRequest(
    version=30,
    buildhash="abc123",
    os=platform.system().lower(),
    install_id=1234567890123,
    last_message_id=0,
)
resp = requests.post(
    "https://ankiweb.net/svc/desktop/check-for-update",
    data=req.SerializeToString(),
    timeout=60,
)
resp.raise_for_status()
out = CheckForUpdateResponse()
out.ParseFromString(resp.content)
print(out)
```

---

## Operational considerations

- **Rate limits / ToS:** Not documented here—use sparingly and respect service policies.
- **Request cap:** Add-on info allows max 25 IDs per call (per proto comment).
- **Error handling:** Server is expected to return non-2xx on errors; client uses `error_for_status()` before decoding.
- **Timeout:** 60 seconds.
- **Binary payloads:** These endpoints are protobuf-only; no JSON variant is exposed in the OSS client.

---

## What’s _not_ here

- Full sync protocol and media sync are implemented elsewhere and use different endpoints and auth; out of scope for this doc.
- AnkiHub APIs (`app.ankihub.net/api/`) are separate; see `rslib/src/ankihub/http_client` for those.

---

## Other non-`/svc/` AnkiWeb URLs referenced by the desktop app (not protobuf APIs)

- Shared deck landing page: `https://ankiweb.net/shared/`
- Shared deck info page: `https://ankiweb.net/shared/info/{id}`
- Desktop update download page (fallback): `https://ankiweb.net/update/desktop`
- Account register link (UI): `https://ankiweb.net/account/register`

---

## References (source locations)

- Rust client for AnkiWeb: `rslib/src/backend/ankiweb.rs`
- Protobuf definitions: `proto/anki/ankiweb.proto`
- HTTP client (general): `pylib/anki/httpclient.py`
- GUI sync login (links AnkiWeb register page): `qt/aqt/sync.py`
- Other AnkiWeb URLs/constants: `qt/aqt/__init__.py`, `qt/aqt/addons.py`, `qt/aqt/update.py`
- Sync HTTP client (separate endpoint): `rslib/src/sync/http_client/`

---

## License / redistribution

The Anki repo is AGPL-3.0. If you incorporate or modify this client logic in a deployed service, ensure your usage complies with AGPL (e.g., make source available to users interacting with the modified networked software) and with AnkiWeb’s terms of service.

---
