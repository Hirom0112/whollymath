# infrastructure/

AWS CDK (TypeScript) defining the deployed system: S3 + CloudFront (frontend), ECS Fargate + ALB (backend), RDS Postgres (data), S3 (ML artifacts), Secrets Manager (TECH_STACK §7). One stack per concern (CLAUDE.md §10). A pnpm workspace package.

Does NOT live here: application code (`backend/`, `frontend/`), secrets (use Secrets Manager — never commit), or local-dev config (that is `docker-compose.yml` + `.env` at repo root).

## Deploy + verify (read before `cdk deploy`)

Deploys are **manual** today: `cd infrastructure && AWS_PROFILE=whollymath npx cdk deploy --all` (Docker must be running). `ci.yml` only lints/tests — it does NOT deploy.

**After any `cdk deploy`, verify the apex domain `https://whollymath.app` (and `www`), not just the `*.cloudfront.net` URL.** `cdk deploy` resets the CloudFront distribution to its code-defined state, so anything attached by hand in the console is reverted. A V2 deploy once stripped the `whollymath.app` alias + ACM cert because they had been attached out-of-band at first launch and were not declared in the CDK; the app stayed healthy while the apex domain failed TLS. They are now declared in `lib/app-stack.ts` (`domainNames` + `certificate` on the `Distribution`). **Rule: the CDK is the source of truth — never configure CloudFront/ALB/RDS by hand in the console; add it to the stack instead.** The only protected exception is the secret *values* in Secrets Manager.
