# Contributing to AdLab

Thanks for looking at this project. It's a learning environment first, so contributions that make
it clearer, more correct, or easier to run locally are all welcome — not just new features.

## Before you start

Skim the [README](README.md), especially **Known limitations** and **Design versus
implementation**. Several gaps are already known and tracked there rather than in issues; if you
want to pick one up, open an issue first so two people don't work on the same thing.

## Setting up

```bash
git clone https://github.com/brunooffs/adlab-lab.git
cd adlab-lab
./start.sh
bin/smoke.sh
```

See the README's [Quick start](README.md#quick-start) and [Profiles](README.md#choose-what-to-run-profiles)
sections for the rest. You do not need Node, Python, or JVM installed locally — the API, producer,
and Spark job all run in containers.

## Making a change

1. Create a branch off `main`.
2. Keep the change scoped — a patch that fixes one thing is much easier to verify than one that
   fixes three.
3. If you're changing `docker-compose.yml`, a Dockerfile, or anything under `bin/`, `spark/`, or
   `spark-jobs/`, validate it locally before opening a PR:

   | You touched | Run |
   |---|---|
   | anything in the core profile (API, Postgres, Redis, Mongo, Elasticsearch) | `bin/smoke.sh` |
   | Kafka, Spark, the producer, or the aggregate indices | `./start.sh streaming` then `bin/e2e.sh` |
   | Kibana data views or the dashboard | `bin/setup-kibana.sh`, then check the dashboard renders |
   | `k8s/` | see [Kubernetes and GitOps](README.md#kubernetes-and-gitops-experimental) — this part
     is still experimental, so say so in your PR if you haven't fully verified it |

   `bin/e2e.sh` resets the aggregate indices and Spark checkpoints, and takes about a minute.

4. Commit messages: a short imperative summary is enough (`Fix Kafka UI healthcheck timeout`, not
   `fixes`). Reference the issue number if there is one.

## Opening a PR

Say what you tested and how (paste the relevant `bin/smoke.sh` or `bin/e2e.sh` output). A PR that
changes behavior with no evidence it was run is harder to review and slower to merge.

CI runs type-checking and config validation automatically; you don't need to reproduce that
locally, only the parts in the table above that CI doesn't cover yet (the full pipeline).

## Reporting a bug

Include:
- the command you ran and the full output (not just the last line)
- `./status.sh` output if a service seems unhealthy
- your OS and Docker version (`docker version`)

If `bin/e2e.sh` failed, it saves logs to `.e2e-logs/<topic>/` — attach the relevant file instead of
retyping it.

## Good first issues

Things that are real, scoped, and don't require deep context:
- Wire Cassandra as the raw click-event store (schema is in `docs/ad-click-aggregator-schemas.docx`)
- Have Spark write the Redis speed-layer keys that `/v1/metrics/clicks` already reads
- Add event-ID deduplication in the producer or the Spark job
- Improve `status.sh` to show all running containers, not just the first 15

If you want to take on something bigger (a tutorial chapter, the Kubernetes pass, Prisma 7), open an
issue first to check it's not already in progress.

## Code of conduct

Be respectful, assume good faith, and keep discussion focused on the project. This is a small,
personal learning project — treat it accordingly.
