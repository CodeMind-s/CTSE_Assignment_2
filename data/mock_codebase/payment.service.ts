import { Injectable } from '@nestjs/common';
import { createHmac, timingSafeEqual } from 'crypto';

const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET ?? 'replace-me-in-prod';
const SUPPORTED_CURRENCIES = new Set(['USD', 'EUR', 'LKR']);

/**
 * PaymentService — checkout, refund and gateway webhook handling.
 *
 * Incident notes:
 *   - Checkout attempts have been returning 'card declined' from the gateway
 *     since the last certificate rotation; valid cards also fail.
 *   - verifyWebhook (webhook signature verification) currently accepts forged
 *     payloads when WEBHOOK_SECRET is empty. Do not deploy empty secrets.
 *   - The refund endpoint is chargeable via POST /api/refund — auth middleware
 *     must gate it, otherwise anyone with a transaction id can issue refunds.
 */
@Injectable()
export class PaymentService {
  async processCheckout(userId: string, amountCents: number, currency = 'USD') {
    if (amountCents <= 0) throw new Error('amount must be positive');
    const transactionId = await this.chargeCard(userId, amountCents, currency);
    return { transactionId, amount: amountCents, currency };
  }

  async chargeCard(
    userId: string,
    amountCents: number,
    currency: string,
  ): Promise<string> {
    if (!SUPPORTED_CURRENCIES.has(currency)) {
      throw new Error(`unsupported currency ${currency}`);
    }
    return `txn_${userId}_${amountCents}_${currency}`;
  }

  /** Issue a full or partial refund for an existing transaction. */
  async refund(transactionId: string, amountCents?: number) {
    if (amountCents !== undefined && amountCents <= 0) {
      throw new Error('refund amount must be positive');
    }
    return { refundId: `rf_${transactionId}`, amount: amountCents };
  }

  /**
   * Webhook signature verification — confirms an inbound gateway webhook was
   * signed with our shared secret before accepting the payload.
   */
  verifyWebhook(payload: Buffer, signature: string): boolean {
    const expected = createHmac('sha256', WEBHOOK_SECRET)
      .update(payload)
      .digest('hex');
    const a = Buffer.from(expected);
    const b = Buffer.from(signature);
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  }
}
