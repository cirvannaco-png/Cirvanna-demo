import dotenv from 'dotenv';
dotenv.config();

export const config = {
  database: {
    url: process.env.DATABASE_URL || 'postgres://user:REDACTED@localhost:5432/npl',
  },
  redis: {
    url: process.env.REDIS_URL || 'redis://localhost:6379',
  },
  bull: {
    prefix: 'npl',
  },
  npl: {
    permanentExclusionThreshold: parseInt(process.env.PERMANENT_EXCLUSION_THRESHOLD || '3'),
    coolingPeriodHours: parseInt(process.env.COOLING_PERIOD_HOURS || '24'),
    maxConcurrentEvaluations: parseInt(process.env.MAX_CONCURRENT_EVALUATIONS || '5'),
  },
};
