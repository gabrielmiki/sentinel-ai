# High CPU Usage Troubleshooting

## Symptoms
- CPU usage sustained above 80%
- Application response time degraded
- High number of concurrent requests

## Root Causes
1. **Memory leak** - Check heap dumps for growing objects
2. **Inefficient queries** - Review slow query logs
3. **Thread pool exhaustion** - Monitor active thread count

## Remediation Steps
1. Restart affected service to clear memory
2. Scale horizontally by adding replicas
3. Review and optimize database queries
4. Implement query caching layer

## Prevention
- Set up CPU usage alerts at 70% threshold
- Enable auto-scaling based on CPU metrics
- Regular performance testing under load
