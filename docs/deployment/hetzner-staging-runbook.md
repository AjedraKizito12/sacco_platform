# Hetzner Staging Runbook

One-time provisioning + ongoing deploys for the SACCO staging environment.
Design: `docs/superpowers/specs/2026-07-16-staging-deployment-design.md`.

## 1. Provision the VPS (once)

1. Create a Hetzner **CPX41** (8 vCPU / 16 GB), Ubuntu 24.04.
2. DNS: add two `A` records pointing at the VPS IPv4:
   - `staging.<domain>`
   - `api-staging.<domain>`
3. SSH in as root; create a deploy user and harden SSH:
   ```bash
   adduser --disabled-password --gecos "" deploy
   usermod -aG sudo deploy
   rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
   # disable password + root SSH login in /etc/ssh/sshd_config, then: systemctl reload ssh
   ```
4. Firewall:
   ```bash
   ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
   ```
5. Install Docker Engine + compose plugin (get.docker.com), then
   `usermod -aG docker deploy`.

## 2. First deploy (as `deploy`)

```bash
git clone <repo-url> sacco-platform && cd sacco-platform
STAGING_DOMAIN=<domain> scripts/gen_staging_env.sh
# edit .env.staging: set CADDY_ACME_EMAIL
scripts/deploy.sh
make staging-seed-admin EMAIL=admin@<domain>   # prompts for a password
```

Wait for Caddy to obtain certs (first request to each subdomain triggers ACME),
then open `https://staging.<domain>` and log in with the seeded admin.

## 3. Ongoing deploys

```bash
scripts/deploy.sh    # or: make deploy
```

## 4. Operations

- Logs: `make staging-logs SVC=api` (or `worker`, `beat`, `portal`, `caddy`).
- Reset a superuser password: `make staging-seed-admin EMAIL=<email>`.
- Stop/start: `make staging-down` / `make staging-up`.

## Out of scope (roadmap Phases 4–6)

Automated backups (data is in named volumes only), observability, rate limiting,
CI/CD. Losing the VPS loses staging data until Phase 4 ships.
