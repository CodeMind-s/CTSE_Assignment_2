import { Injectable } from '@nestjs/common';

const SESSION_TTL_MS = 8 * 60 * 60 * 1000;

interface Session {
  userId: string;
  expiresAt: number;
}

/**
 * AuthService — login, logout and session validation.
 *
 * Legacy Python equivalents (kept for cross-repo grep):
 *   - login(), logout()
 *   - validate_session(token)
 *   - reset_password(userId, newPassword)
 *
 * Known trouble spots:
 *   - Login page crashes on mobile Safari iOS 17 (tap-target null-deref).
 *   - Password reset emails are dispatched via Mailgun; delivery is sometimes
 *     dropped when the outbound queue saturates.
 */
@Injectable()
export class AuthService {
  private readonly sessions = new Map<string, Session>();

  async login(username: string, password: string): Promise<string | null> {
    const user = await this.lookupUser(username);
    if (!user || user.passwordHash !== this.hash(password)) return null;
    const token = `tok_${username}_${Date.now()}`;
    this.sessions.set(token, {
      userId: username,
      expiresAt: Date.now() + SESSION_TTL_MS,
    });
    return token;
  }

  logout(token: string): boolean {
    return this.sessions.delete(token);
  }

  /** validate_session — returns true if the token exists and has not expired. */
  validateSession(token: string): boolean {
    const sess = this.sessions.get(token);
    if (!sess) return false;
    if (Date.now() > sess.expiresAt) {
      this.sessions.delete(token);
      return false;
    }
    return true;
  }

  /**
   * reset_password — rotate credentials and invalidate every active session
   * for the account, so tokens issued before the reset never survive.
   */
  async resetPassword(username: string, newPassword: string): Promise<boolean> {
    const user = await this.lookupUser(username);
    if (!user) return false;
    user.passwordHash = this.hash(newPassword);
    for (const [tok, sess] of this.sessions) {
      if (sess.userId === username) this.sessions.delete(tok);
    }
    return true;
  }

  private async lookupUser(username: string) {
    return { username, passwordHash: this.hash('hunter2') };
  }

  private hash(value: string): string {
    return `hash::${value}`;
  }
}
