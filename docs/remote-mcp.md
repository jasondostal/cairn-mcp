# Remote MCP Access — OAuth2 Authorization Server

Connect Cairn to Claude.ai, the Claude mobile app, or any MCP client that supports OAuth2.

Cairn acts as an **OAuth2 Authorization Server** while delegating user authentication to your existing OIDC identity provider (Authentik, Keycloak, Auth0, Okta, Azure AD, etc.).

## How it works

```
MCP Client (Claude.ai)                 Cairn                    Identity Provider
       |                                 |                            |
       |-- GET /mcp ------------------>  |                            |
       |<- 401 WWW-Authenticate: Bearer  |                            |
       |                                 |                            |
       |-- GET /.well-known/oauth-*  --> |  (discovery)               |
       |<- metadata (issuer, endpoints)  |                            |
       |                                 |                            |
       |-- POST /register -------------> |  (Dynamic Client Reg)      |
       |<- client_id, client_secret      |                            |
       |                                 |                            |
       |-- GET /authorize?... ---------> |                            |
       |                                 |-- redirect to IdP -------> |
       |                                 |                            |
       |                                 |  (user logs in)            |
       |                                 |                            |
       |                                 |<- /oauth/callback -------- |
       |<- redirect with auth code       |                            |
       |                                 |                            |
       |-- POST /token ----------------> |  (exchange code for JWT)   |
       |<- access_token, refresh_token   |                            |
       |                                 |                            |
       |-- POST /mcp (Bearer token) ---> |  (authenticated MCP)      |
```

The flow uses **Authorization Code + PKCE** with **Dynamic Client Registration** (RFC 7591). Cairn issues its own JWTs — the same tokens used by the web UI and API. Existing auth methods (proxy header, API key, PAT) continue working alongside OAuth2.

## Prerequisites

1. **Auth enabled** — `CAIRN_AUTH_ENABLED=true`
2. **OIDC configured** — `CAIRN_OIDC_ENABLED=true` with a working identity provider
3. **Public URL set** — `CAIRN_PUBLIC_URL=https://your-domain.com` (must be HTTPS)
4. **Redirect URI registered** — Add `https://your-domain.com/oauth/callback` to your OIDC provider's allowed redirect URIs

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_MCP_OAUTH_ENABLED` | `false` | Enable the OAuth2 Authorization Server |
| `CAIRN_MCP_OAUTH_ACCESS_EXPIRY` | `86400` | Access token lifetime in seconds (default: 24 hours) |
| `CAIRN_MCP_OAUTH_REFRESH_EXPIRY` | `2592000` | Refresh token lifetime in seconds (default: 30 days) |

Add to your `.env` or `docker-compose.yml`:

```bash
CAIRN_MCP_OAUTH_ENABLED=true
# Optional: customize token lifetimes
# CAIRN_MCP_OAUTH_ACCESS_EXPIRY=86400
# CAIRN_MCP_OAUTH_REFRESH_EXPIRY=2592000
```

## Connecting from Claude.ai

1. Open [Claude.ai](https://claude.ai) > Settings > Integrations
2. Click "Add custom MCP" (or equivalent)
3. Enter your Cairn MCP URL: `https://your-domain.com/mcp`
4. Claude.ai will discover the OAuth2 endpoints and start the authorization flow
5. You'll be redirected to your identity provider to log in
6. After login, Claude.ai receives tokens and connects to your MCP tools

If your identity provider supports SSO sessions (e.g., you're already logged in via the Cairn web UI), the auth redirect is invisible — you won't see a login page.

## OIDC Provider Setup

### Adding the redirect URI

Your OIDC provider needs to allow Cairn's OAuth callback URL. Add this to your provider's redirect URI list:

```
https://your-domain.com/oauth/callback
```

Provider-specific guidance:

| Provider | Where to add |
|----------|-------------|
| **Authentik** | Applications > Your Provider > Protocol Settings > Redirect URIs |
| **Keycloak** | Clients > Your Client > Valid Redirect URIs |
| **Auth0** | Applications > Your App > Settings > Allowed Callback URLs |
| **Okta** | Applications > Your App > General > Login Redirect URIs |
| **Azure AD** | App Registrations > Your App > Authentication > Redirect URIs |

The same OIDC client (client_id/secret) used for Cairn's web UI login works for the OAuth2 server — no additional OIDC application is needed.

## Reverse Proxy Configuration

If Cairn sits behind a reverse proxy (nginx, Caddy, Traefik), you need to route the OAuth2 endpoints to the Cairn backend. These paths must be accessible:

```
/.well-known/oauth-authorization-server
/.well-known/oauth-protected-resource
/authorize
/token
/register
/revoke
/oauth/callback
/mcp
```

### nginx example

```nginx
# OAuth2 discovery
location /.well-known/oauth-authorization-server {
    proxy_pass http://cairn:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /.well-known/oauth-protected-resource {
    proxy_pass http://cairn:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

# OAuth2 endpoints
location ~ ^/(authorize|token|register|revoke|oauth/callback)$ {
    proxy_pass http://cairn:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# MCP endpoint (SSE-capable)
location /mcp {
    proxy_pass http://cairn:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 86400;
}
```

## Security Hardening

The OAuth2 server includes application-level protections, but production deployments should add infrastructure-level hardening.

### Built-in protections

- **HTTPS-only redirect URIs** — Dynamic Client Registration rejects `http://` redirect URIs
- **Localhost rejection** — redirect URIs targeting `localhost`, `127.0.0.1`, `::1` are blocked
- **Client registration cap** — maximum 50 registered clients to prevent DCR spam
- **Expired token cleanup** — refresh tokens are rejected and deleted when expired
- **PKCE required** — Authorization Code flow uses PKCE (code_challenge/code_verifier)
- **One-time auth codes** — authorization codes are consumed on use and expire after 5 minutes

### Recommended: Rate limiting

Add rate limits to OAuth2 endpoints at the reverse proxy level:

```nginx
# In the http block
limit_req_zone $binary_remote_addr zone=oauth_register:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=oauth_token:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=oauth_authorize:10m rate=10r/m;

# On the location blocks
location /register {
    limit_req zone=oauth_register burst=2 nodelay;
    # ... proxy_pass ...
}

location /token {
    limit_req zone=oauth_token burst=10 nodelay;
    # ... proxy_pass ...
}

location /authorize {
    limit_req zone=oauth_authorize burst=5 nodelay;
    # ... proxy_pass ...
}
```

### Recommended: fail2ban

If you're using fail2ban with nginx, enable the `nginx-limit-req` jail to auto-ban IPs that repeatedly trigger rate limits:

```ini
[nginx-limit-req]
enabled = true
maxretry = 10
findtime = 600
bantime = 3600
```

This bans IPs for 1 hour after 10 rate-limit violations in 10 minutes.

## Troubleshooting

### "Error connecting to the MCP server"

1. Verify Cairn is running and accessible at your public URL
2. Check that `CAIRN_MCP_OAUTH_ENABLED=true` is set (look for "OAuth2 Authorization Server enabled" in startup logs)
3. Confirm the redirect URI is registered with your OIDC provider
4. Check reverse proxy is routing all OAuth2 paths (especially `/.well-known/oauth-protected-resource`)

### OAuth2 not initializing (logs show "legacy middleware")

The `MCPOAuthConfig` requires `CAIRN_MCP_OAUTH_ENABLED` to be set in the container's environment, not just in `.env`. Verify it's passed through in your `docker-compose.yml`.

### `/register` returning 500

Check Cairn logs — this usually means the migration hasn't run. Verify that `053_oauth2_clients.sql` has been applied (migrations run automatically on startup).

### Token refresh failing

Refresh tokens expire after 30 days by default. If a client hasn't connected in that time, they'll need to re-authenticate. Adjust with `CAIRN_MCP_OAUTH_REFRESH_EXPIRY`.

## Database schema

Migration `053_oauth2_clients.sql` creates:

- `oauth2_clients` — registered OAuth2 clients (client_id, secret, metadata)
- `oauth2_refresh_tokens` — active refresh tokens with expiry tracking

Both tables are managed automatically. Expired refresh tokens are cleaned up on access.

## Backward compatibility

- `CAIRN_MCP_OAUTH_ENABLED=false` (default): zero behavior change
- When enabled: all existing auth methods (proxy header, API key, PAT, JWT) continue working
- The web UI OIDC login flow is completely unaffected
- Local MCP clients (stdio, direct HTTP) work as before
