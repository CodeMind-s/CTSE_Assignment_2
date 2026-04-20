import { Body, Controller, Get, Headers, Post } from '@nestjs/common';
import { AuthService } from './auth.service';
import { PaymentService } from './payment.service';

/**
 * ApiController — public HTTP surface.
 *
 * Known issues:
 *   - An unknown route currently returns 500 instead of a clean 404 JSON
 *     envelope. The catch-all handler must be registered at module bootstrap.
 *   - The rate limiter keys on X-Forwarded-For without validating the upstream
 *     proxy, so the per-IP cap can be bypassed by varying that header.
 */
@Controller('api')
export class ApiController {
  constructor(
    private readonly auth: AuthService,
    private readonly payments: PaymentService,
  ) {}

  @Get('health')
  health() {
    return { ok: true };
  }

  @Post('login')
  async loginRoute(@Body() body: { username: string; password: string }) {
    const token = await this.auth.login(body.username, body.password);
    if (!token) {
      return { status: 401, body: { error: 'invalid credentials' } };
    }
    return { status: 200, body: { token } };
  }

  @Post('refund')
  async refundRoute(
    @Body() body: { transactionId: string; amount?: number },
    @Headers('authorization') authHeader?: string,
  ) {
    // AuthMiddleware should already have gated this route; belt-and-braces here.
    const token = (authHeader ?? '').replace(/^Bearer\s+/, '');
    if (!this.auth.validateSession(token)) {
      return { status: 401, body: { error: 'unauthorized' } };
    }
    return this.payments.refund(body.transactionId, body.amount);
  }

  @Get('*')
  notFound() {
    // Returns a clean 404 envelope instead of bubbling an unknown route as 500.
    return { status: 404, body: { error: 'not found' } };
  }
}
