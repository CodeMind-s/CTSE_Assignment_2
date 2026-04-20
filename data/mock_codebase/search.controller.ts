import { Controller, Get, Query } from '@nestjs/common';

/**
 * SearchController — /api/search endpoint.
 *
 * Known issues:
 *   - Search endpoint p95 latency jumped from 200ms to 1.8s after the index
 *     rebuild last night. CPU on the search nodes is flat, so the regression
 *     is suspected to be a pagination / fan-out problem.
 */
@Controller('api/search')
export class SearchController {
  @Get()
  async search(@Query('q') q: string) {
    if (!q || q.length < 2) return { results: [] };
    // TODO(performance): this path is the p95 latency regression hot spot.
    return { results: await this.runSearch(q) };
  }

  private async runSearch(q: string) {
    return [{ hit: q }];
  }
}
