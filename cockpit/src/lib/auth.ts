const TOKEN_COOKIE = 'cogmem_token';
const LOGIN_URL = 'https://cogmem.ai/login';

/**
 * Read the JWT from the shared .cogmem.ai domain cookie.
 */
export function getToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${TOKEN_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Clear the JWT cookie and redirect to the marketing site login page.
 */
export function logout(): void {
  document.cookie = `${TOKEN_COOKIE}=; domain=.cogmem.ai; path=/; max-age=0; secure; samesite=lax`;
  window.location.href = LOGIN_URL;
}

/**
 * Decode the JWT payload (without verification — verification happens server-side).
 */
export function decodeToken(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

export interface TokenUser {
  sub: string;       // user UUID
  email?: string;
  full_name?: string;
  exp?: number;
}

/**
 * Get user info from the JWT. Returns null if no valid token.
 */
export function getTokenUser(): TokenUser | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeToken(token);
  if (!payload) return null;
  // Check expiry
  if (payload.exp && (payload.exp as number) * 1000 < Date.now()) {
    logout();
    return null;
  }
  return payload as unknown as TokenUser;
}
