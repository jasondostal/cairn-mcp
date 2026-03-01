/**
 * Next.js middleware for auth route protection (ca-124).
 *
 * Client-side only — checks localStorage token presence via cookie proxy.
 * The actual JWT validation happens server-side in the API middleware.
 *
 * Note: Next.js middleware runs on the edge and can't access localStorage.
 * Auth checks happen client-side in the AuthGuard component instead.
 * This file is kept minimal — just a no-op export for future server-side
 * session cookies if needed.
 */

export { };
