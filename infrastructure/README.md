# infrastructure/

AWS CDK (TypeScript) defining the deployed system: S3 + CloudFront (frontend), ECS Fargate + ALB (backend), RDS Postgres (data), S3 (ML artifacts), Secrets Manager (TECH_STACK §7). One stack per concern (CLAUDE.md §10). A pnpm workspace package.

Does NOT live here: application code (`backend/`, `frontend/`), secrets (use Secrets Manager — never commit), or local-dev config (that is `docker-compose.yml` + `.env` at repo root).
