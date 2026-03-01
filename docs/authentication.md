# Authentication Guide

Cairn supports multiple authentication modes, from zero-config local development
to enterprise SSO. Choose what fits your deployment.

## Overview

| Mode | Use case | Complexity |
|------|----------|------------|
| No auth (default) | Local development, single user | None |
| Static API key | Simple shared-secret protection | 2 env vars |
| Local auth (JWT) | Multi-user with username/password | 3 env vars |
| Personal Access Tokens | Machine clients (CI, agents, scripts) | Enabled via local auth |
| OIDC / SSO | Enterprise identity provider integration | 6+ env vars |
| Stdio identity | MCP stdio transport sessions | 1 env var |

All modes can be combined. When multiple modes are enabled, Cairn tries each
in order: static API key, JWT, Personal Access Token.

## Security Notice

> Cairn's authentication system is functional and tested in production environments,
> but it has **not been independently audited**. If you are deploying Cairn on a
> network accessible to untrusted users, layer additional protections:
>
> - TLS termination via a reverse proxy (nginx, Caddy, Traefik)
> - Network segmentation and firewall rules
> - Regular rotation of secrets and tokens
>
> Do not rely on Cairn auth as your sole security boundary for sensitive data.

---

## Mode 1: No Authentication (Default)

Out of the box, Cairn runs with authentication disabled. All endpoints are open.

```bash
CAIRN_AUTH_ENABLED=false   # default
```

This is appropriate for:
- Local development on `localhost`
- Single-user deployments on a trusted network
- Evaluation and testing

No configuration needed. Skip to [MCP Client Configuration](#mcp-client-configuration)
if you just want to connect a client.

---

## Mode 2: Static API Key

The simplest form of protection. All `/api` routes require a key in an HTTP header.
Health (`/api/status`) and docs (`/api/swagger`) remain exempt.

```bash
CAIRN_AUTH_ENABLED=true
CAIRN_API_KEY=your-secret-key-here
# CAIRN_AUTH_HEADER=X-API-Key   # default header name
```

### Usage

```bash
curl -H "X-API-Key: your-secret-key-here" https://cairn.example.com/api/status
```

### MCP client config

```json
{
  "mcpServers": {
    "cairn": {
      "url": "https://cairn.example.com/mcp",
      "headers": {
        "X-API-Key": "your-secret-key-here"
      }
    }
  }
}
```

> **Note:** The static API key is checked before JWT/PAT resolution. It provides
> a simple shared secret but does not support per-user identity or RBAC. For
> multi-user scenarios, use local auth or OIDC instead.

---

## Mode 3: Local Authentication (JWT)

Full multi-user authentication with username/password login, JWT tokens, and
role-based access control. First user to register becomes the admin.

### Setup

```bash
CAIRN_AUTH_ENABLED=true
CAIRN_AUTH_JWT_SECRET=<random-secret>
# CAIRN_AUTH_JWT_EXPIRE_MINUTES=1440   # 24 hours, default
```

Generate a secure JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# or
openssl rand -base64 32
```

### First-user setup

When auth is enabled and no users exist, the login page shows a registration
form. The first user created automatically receives the `admin` role.

**Via the web UI:** Navigate to `/login` and complete the registration form.

**Via the API:**

```bash
curl -X POST https://cairn.example.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secure-password", "email": "alice@example.com"}'
```

### Login

```bash
curl -X POST https://cairn.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secure-password"}'
```

Response:

```json
{
  "access_token": "eyJ0eXAiOiJKV1Qi...",
  "token_type": "bearer",
  "user": {"id": 1, "username": "alice", "role": "admin", "email": "alice@example.com"}
}
```

Use the token in subsequent requests:

```bash
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1Qi..." \
  https://cairn.example.com/api/auth/me
```

### Roles

| Role | Capabilities |
|------|-------------|
| `admin` | Full access. Manage users, view all projects, modify settings. |
| `user` | Access own projects and memories. Create PATs. |
| `agent` | Scoped to assigned projects. Used for automated clients. |

Admins can create additional users and assign roles via the Users page
(`/admin/users`) or the API:

```bash
curl -X POST https://cairn.example.com/api/auth/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"username": "bob", "password": "bobs-password", "role": "user"}'
```

---

## Mode 4: Personal Access Tokens (PATs)

Long-lived tokens for machine clients — CI pipelines, scripts, MCP clients,
background agents. PATs are scoped to the creating user's identity and
permissions.

### Prerequisites

Local auth must be enabled (Mode 3). PATs are created by authenticated users.

### Creating a token

**Via the web UI:** Go to Settings (`/settings`) and use the "Personal Access
Tokens" section.

**Via the API:**

```bash
curl -X POST https://cairn.example.com/api/auth/tokens \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-pipeline", "expires_in_days": 90}'
```

Response:

```json
{
  "raw_token": "cairn_a1b2c3d4e5f6...",
  "name": "ci-pipeline",
  "token_prefix": "cairn_a1b2c3",
  "expires_at": "2026-06-01T00:00:00Z"
}
```

> **Important:** The full token is only shown once. Store it securely.

### Token format

- Prefix: `cairn_` followed by 48 hex characters
- Storage: SHA-256 hash (the raw token is never stored)
- Display: first 12 characters shown as prefix for identification

### Using PATs

PATs are used as Bearer tokens, just like JWTs:

```bash
curl -H "Authorization: Bearer cairn_a1b2c3d4e5f6..." \
  https://cairn.example.com/api/status
```

### MCP client config with PAT

```json
{
  "mcpServers": {
    "cairn": {
      "url": "https://cairn.example.com/mcp",
      "headers": {
        "Authorization": "Bearer cairn_a1b2c3d4e5f6..."
      }
    }
  }
}
```

### Managing tokens

```bash
# List your tokens
curl -H "Authorization: Bearer <jwt>" \
  https://cairn.example.com/api/auth/tokens

# Revoke a token
curl -X DELETE -H "Authorization: Bearer <jwt>" \
  https://cairn.example.com/api/auth/tokens/3
```

The Settings page provides a UI for listing and revoking tokens.

---

## Mode 5: OIDC / SSO

Cairn supports OpenID Connect (OIDC) for single sign-on with external identity
providers. The implementation uses the Authorization Code flow with PKCE
(Proof Key for Code Exchange) for security.

**Provider compatibility:** Cairn works with any OIDC-compliant identity provider.
It has been tested with [Authentik](https://goauthentik.io/). Other providers
such as Keycloak, Auth0, Okta, and Azure AD should work but have not been
explicitly tested. If you encounter provider-specific issues, please report them.

### Prerequisites

- Local auth enabled (Mode 3) — OIDC users get Cairn JWTs after SSO
- An OIDC provider configured with a client application for Cairn

### Environment variables

```bash
CAIRN_AUTH_ENABLED=true
CAIRN_AUTH_JWT_SECRET=<random-secret>

CAIRN_OIDC_ENABLED=true
CAIRN_OIDC_PROVIDER_URL=https://auth.example.com/application/o/cairn/
CAIRN_OIDC_CLIENT_ID=<client-id>
CAIRN_OIDC_CLIENT_SECRET=<client-secret>
# CAIRN_OIDC_SCOPES=openid email profile         # default
# CAIRN_OIDC_DEFAULT_ROLE=user                     # role for new OIDC users
# CAIRN_OIDC_ADMIN_GROUPS=cairn-admins             # IdP groups that map to admin role
# CAIRN_OIDC_AUTO_CREATE_USERS=true                # auto-provision on first login
```

### Setting up your OIDC provider

The general steps apply to any OIDC provider:

1. **Create an OAuth2/OIDC application** in your identity provider
   - Application type: **Web application** (confidential client)
   - Grant type: **Authorization Code**
   - Enable **PKCE** (S256 challenge method)

2. **Configure the redirect URI:**
   ```
   https://cairn.example.com/api/auth/oidc/callback
   ```
   Replace with your Cairn instance's public URL.

3. **Configure scopes:** Ensure `openid`, `email`, and `profile` scopes are available.

4. **Note the following values** from your provider:
   - **Discovery URL** (OpenID Configuration endpoint) — typically ends in
     `/.well-known/openid-configuration`. Set `CAIRN_OIDC_PROVIDER_URL` to the
     base path (without `/.well-known/openid-configuration`).
   - **Client ID** and **Client Secret**

5. **Group-to-role mapping (optional):** If your provider includes group
   memberships in the `groups` claim of the ID token, set `CAIRN_OIDC_ADMIN_GROUPS`
   to a comma-separated list of group names that should receive the `admin` role
   in Cairn. Users not in these groups get the role specified by
   `CAIRN_OIDC_DEFAULT_ROLE` (default: `user`).

6. **OIDC group sync (automatic):** When the ID token includes a `groups` claim,
   Cairn automatically syncs group membership on every login:
   - Groups from the claim are created in Cairn if they don't exist (source: `oidc`)
   - The user is added to all claimed groups
   - The user is removed from OIDC-sourced groups no longer present in the claim

   This keeps Cairn group membership in sync with your identity provider. Groups
   created via OIDC sync can be assigned project access from the Groups admin page
   (`/admin/groups`), giving you IdP-driven project authorization.

### Reverse proxy / CAIRN_PUBLIC_URL

When Cairn runs behind a reverse proxy, the server's internal address differs
from the public URL that browsers use. The OIDC callback URL must match what
the browser sees.

The web UI handles this automatically — it sends `window.location.origin` as
the callback base. For direct API calls (e.g., testing with curl), set:

```bash
CAIRN_PUBLIC_URL=https://cairn.example.com
```

This tells Cairn its externally-reachable URL for constructing callback URIs
when no browser origin is available.

### How the OIDC flow works

```
Browser                    Cairn                     OIDC Provider
   |                         |                            |
   |-- GET /auth/oidc/login ->|                            |
   |                         |-- generate PKCE verifier -->|
   |<- authorization_url ----|                            |
   |                         |                            |
   |-- redirect to provider -------------------------------->|
   |                         |                            |
   |<- redirect with code -----------------------------------|
   |                         |                            |
   |-- GET /auth/oidc/callback?code=...&state=... -------->|
   |                         |-- exchange code + verifier ->|
   |                         |<- ID token + access token ---|
   |                         |                            |
   |                         |-- validate ID token         |
   |                         |-- get/create user           |
   |                         |-- issue Cairn JWT           |
   |<- redirect to UI with JWT                            |
```

### User provisioning

On first OIDC login, Cairn provisions a user account:

1. **Match by external ID** — checks if the OIDC subject (`sub` claim) is already
   linked to a Cairn user
2. **Match by email** — if no external ID match, checks if a local user with the
   same email exists and links the OIDC identity to it
3. **Create new user** — if neither match, creates a new Cairn user with:
   - Username from the `preferred_username` or `email` claim
   - Role from group mapping or `CAIRN_OIDC_DEFAULT_ROLE`
   - No local password (OIDC-only login)

### Limitations

- The OIDC state store is **in-memory and single-process**. In multi-worker
  deployments, all OIDC login requests must be routed to the same process.
  A shared store (Redis/database) is planned for a future release.
- Token refresh is not yet implemented. Users are re-authenticated when the
  Cairn JWT expires (default: 24 hours).

---

## Mode 6: Stdio Identity

When running Cairn as an MCP server via stdio transport (e.g., directly from
Claude Code), there is no HTTP request to carry authentication headers. The
`CAIRN_STDIO_USER` variable maps stdio sessions to a specific user identity.

```bash
CAIRN_STDIO_USER=alice
```

On startup, Cairn loads the user `alice` from the database and sets that
identity for all stdio MCP requests. This enables RBAC scoping — the user
only sees projects they have access to.

### Requirements

- Auth must be enabled (`CAIRN_AUTH_ENABLED=true`)
- The specified user must exist in the database and be active
- The user is loaded once at startup; changes require a restart

### When to use

- Single-user setups where one person runs the MCP server locally
- Development environments where you want RBAC scoping without tokens
- CI environments that use stdio transport

> **Note:** Stdio identity only applies to the stdio transport. HTTP/REST
> requests still require standard authentication (JWT, PAT, or API key).

---

## Combining Modes

All authentication modes coexist. When a request arrives, Cairn resolves
identity in this order:

1. **Static API key** — if `CAIRN_API_KEY` is set and the request includes a
   matching header, the request is authenticated (no specific user identity)
2. **JWT** — if an `Authorization: Bearer` header is present, try to decode it
   as a Cairn-issued JWT
3. **PAT** — if JWT decoding fails, try to resolve the Bearer token as a
   Personal Access Token

The first successful match wins. If all fail and auth is enabled, the request
is rejected with `401 Unauthorized`.

### Recommended configurations

**Single user, local dev:**
```bash
CAIRN_AUTH_ENABLED=false
```

**Small team, self-managed:**
```bash
CAIRN_AUTH_ENABLED=true
CAIRN_AUTH_JWT_SECRET=<secret>
```

**Enterprise / SSO:**
```bash
CAIRN_AUTH_ENABLED=true
CAIRN_AUTH_JWT_SECRET=<secret>
CAIRN_OIDC_ENABLED=true
CAIRN_OIDC_PROVIDER_URL=https://auth.example.com/application/o/cairn/
CAIRN_OIDC_CLIENT_ID=<id>
CAIRN_OIDC_CLIENT_SECRET=<secret>
CAIRN_OIDC_ADMIN_GROUPS=cairn-admins
CAIRN_PUBLIC_URL=https://cairn.example.com
```

---

## MCP Client Configuration

### Claude Code (stdio)

For stdio transport, no auth headers are needed. Use `CAIRN_STDIO_USER` for
identity (see Mode 6).

### Claude Code (HTTP with PAT)

```json
{
  "mcpServers": {
    "cairn": {
      "url": "https://cairn.example.com/mcp",
      "headers": {
        "Authorization": "Bearer cairn_a1b2c3d4e5f6..."
      }
    }
  }
}
```

### Claude Code (HTTP with API key)

```json
{
  "mcpServers": {
    "cairn": {
      "url": "https://cairn.example.com/mcp",
      "headers": {
        "X-API-Key": "your-secret-key-here"
      }
    }
  }
}
```

### Cursor / other MCP clients

Most MCP clients support a similar `headers` configuration. Provide either
an `Authorization: Bearer <token>` header (JWT or PAT) or the configured
API key header.

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_AUTH_ENABLED` | `false` | Enable authentication |
| `CAIRN_AUTH_JWT_SECRET` | *(empty)* | JWT signing secret. Required when auth is enabled. |
| `CAIRN_AUTH_JWT_EXPIRE_MINUTES` | `1440` | JWT token lifetime in minutes (default 24h) |
| `CAIRN_API_KEY` | *(empty)* | Static API key for simple auth |
| `CAIRN_AUTH_HEADER` | `X-API-Key` | Header name for static API key |
| `CAIRN_PUBLIC_URL` | *(empty)* | Public base URL for OIDC callbacks behind a proxy |
| `CAIRN_OIDC_ENABLED` | `false` | Enable OIDC/SSO |
| `CAIRN_OIDC_PROVIDER_URL` | *(empty)* | OIDC discovery base URL |
| `CAIRN_OIDC_CLIENT_ID` | *(empty)* | OAuth2 client ID |
| `CAIRN_OIDC_CLIENT_SECRET` | *(empty)* | OAuth2 client secret |
| `CAIRN_OIDC_SCOPES` | `openid email profile` | OIDC scopes to request |
| `CAIRN_OIDC_DEFAULT_ROLE` | `user` | Default role for auto-created OIDC users |
| `CAIRN_OIDC_AUTO_CREATE_USERS` | `true` | Auto-create users on first OIDC login |
| `CAIRN_OIDC_ADMIN_GROUPS` | *(empty)* | Comma-separated IdP groups that map to admin role |
| `CAIRN_STDIO_USER` | *(empty)* | Username for MCP stdio transport identity |

---

## Reverse Proxy Configuration

When running Cairn behind a reverse proxy (nginx, Caddy, Traefik), the proxy
needs to route three paths:

| Path | Destination | Purpose |
|------|-------------|---------|
| `/mcp` | cairn backend (port 8000) | MCP protocol for AI agents |
| `/api/terminal/ws/` | cairn backend (port 8000) | WebSocket for web terminal |
| `/` (everything else) | cairn-ui (port 3000) | Web UI + API (Next.js rewrites `/api/*`) |

### nginx example

```nginx
server {
    listen 443 ssl;
    server_name cairn.example.com;

    # MCP protocol — direct to cairn backend
    location /mcp {
        proxy_pass http://cairn:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # WebSocket terminal — direct to cairn backend
    location /api/terminal/ws/ {
        proxy_pass http://cairn:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
    }

    # Everything else — cairn-ui (Next.js handles /api/* rewrites)
    location / {
        proxy_pass http://cairn-ui:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **Important:** Do not place authentication middleware (e.g., Authentik forward
> auth, OAuth2 Proxy) in front of Cairn when using Cairn's built-in auth. Cairn
> manages its own authentication — external auth gates will interfere with the
> OIDC callback flow and MCP client connections.

---

## Troubleshooting

### "JWT secret not configured"

Auth is enabled but `CAIRN_AUTH_JWT_SECRET` is empty. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### OIDC callback returns an error

- Verify the redirect URI in your OIDC provider matches exactly:
  `https://cairn.example.com/api/auth/oidc/callback`
- Check that `CAIRN_OIDC_PROVIDER_URL` points to the correct OIDC discovery
  endpoint (should resolve `/.well-known/openid-configuration`)
- If behind a proxy, set `CAIRN_PUBLIC_URL` to the externally-reachable URL

### OIDC login redirects to wrong URL

This usually means the browser's origin doesn't match what the OIDC provider
expects. Common causes:

- Accessing Cairn via an IP address but the redirect URI uses a hostname
- Proxy rewrites the `Host` header — Cairn uses the browser's
  `window.location.origin` to avoid this, but `CAIRN_PUBLIC_URL` is the
  definitive fallback

### 401 Unauthorized on every request

- Check that your token hasn't expired (default JWT lifetime: 24 hours)
- For PATs, verify the token is active: `GET /api/auth/tokens`
- For API keys, ensure the header name matches `CAIRN_AUTH_HEADER`

### OIDC users don't get admin role

- Verify your IdP includes the `groups` claim in the ID token
- Check that `CAIRN_OIDC_ADMIN_GROUPS` matches the exact group name(s) from
  your IdP (case-sensitive, comma-separated for multiple groups)
- Some providers require explicit configuration to include group claims in tokens

### CORS errors in the browser

If the UI is served from a different origin than the API, add the UI origin
to `CAIRN_CORS_ORIGINS`:

```bash
CAIRN_CORS_ORIGINS=https://cairn.example.com,http://localhost:3000
```
