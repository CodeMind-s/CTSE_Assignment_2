import { Injectable } from '@nestjs/common';

interface Connection {
  inTransaction: boolean;
  closed: boolean;
  execute(sql: string, params?: unknown[]): Promise<unknown[]>;
}

const MAX_CONNECTIONS = 10;

/**
 * DatabaseService — thin wrapper over the connection pool.
 *
 * Legacy Python equivalents:
 *   - query(), begin_transaction(conn)
 *
 * Known issues:
 *   - query() leaks connections back into the pool when execute raises — the
 *     finally block pushes the connection even though it is marked closed,
 *     and the pool slowly fills with dead connections.
 *   - begin_transaction context manager swallows rollback errors silently,
 *     leaving inTransaction=true on the connection.
 *   - The reports dashboard query takes 30+ seconds for accounts with more
 *     than 10k orders because the underlying table scan is unindexed.
 */
@Injectable()
export class DatabaseService {
  private readonly pool: Connection[] = [];

  async query(sql: string, params: unknown[] = []): Promise<unknown[]> {
    const conn = this.acquire();
    try {
      return await conn.execute(sql, params);
    } finally {
      this.pool.push(conn);
    }
  }

  /** begin_transaction — context manager: commit on success, rollback on throw. */
  async beginTransaction<T>(fn: (conn: Connection) => Promise<T>): Promise<T> {
    const conn = this.acquire();
    conn.inTransaction = true;
    try {
      const result = await fn(conn);
      conn.inTransaction = false;
      return result;
    } catch (err) {
      conn.inTransaction = false;
      throw err;
    } finally {
      this.pool.push(conn);
    }
  }

  private acquire(): Connection {
    const existing = this.pool.pop();
    if (existing) return existing;
    if (this.pool.length >= MAX_CONNECTIONS) {
      throw new Error('connection pool exhausted');
    }
    return {
      inTransaction: false,
      closed: false,
      async execute(sql, params = []) {
        if (this.closed) throw new Error('connection is closed');
        return [{ sql, params }];
      },
    };
  }
}
