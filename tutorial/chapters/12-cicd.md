# Chapter 12 — CI/CD with GitHub Actions

## What you'll do

Look at what actually runs on every push and pull request, understand why it's shaped the way it
is, and see two real CI bugs — caught only because CI genuinely ran against a real repository,
not because anyone reasoned their way to them in advance.

```bash
gh workflow view ci.yml   # or just open .github/workflows/ci.yml
```

## One workflow, not three

This repo used to have three separate workflow files with overlapping jobs — the same type-check
duplicated across two of them, the same three weak YAML-parse checks duplicated across another two.
`ci.yml` replaces all three. The cheap jobs — lint, unit tests, config validation — run
unconditionally on every push and pull request, with no path filters to get wrong. Only the
expensive multi-arch image build is gated, and it's gated properly: a dedicated `changes` job using
`dorny/paths-filter` decides whether `api/**` was actually touched, and the build jobs declare
`needs: changes` with an `if:` condition reading that result.

## A permissions bug that took real evidence to diagnose

Adding that `changes` job introduced its own bug. It needs `pull-requests: read` to call GitHub's
API and list a PR's changed files — reasonable. Adding just that one permission broke checkout
entirely, with an error that gave no hint why:

```
remote: Repository not found.
fatal: fatal: repository '...' not found
```

The cause: a job-level `permissions:` block **fully replaces** the workflow-level one for that job
— it does not merge with it. Declaring only `pull-requests: read` silently dropped `contents` to
`none`, and `actions/checkout` needs `contents: read` to fetch the repository at all. GitHub
deliberately returns an ambiguous "not found" rather than a permission-denied message here too — the
same reasoning as the ArgoCD authentication error from Chapter 11, in a completely different
system. The fix is one line: declare `contents: read` explicitly alongside `pull-requests: read`,
every time a job needs anything beyond the workflow default.

## Validating with the real tools, not just YAML syntax

`validate-configs` doesn't just check that `kong.yml` and `prometheus.yml` parse as YAML — that
would pass for a file that's syntactically valid nonsense. It runs the *actual* tools those configs
are meant for, inside their own containers:

```yaml
- run: docker run --rm -v "$PWD/kong/kong.yml:/kong.yml:ro" ... kong:3.9.3-ubuntu kong config parse /kong.yml
- run: docker run --rm -v "$PWD/prometheus/prometheus.yml:..." ... promtool check config ...
```

`shellcheck` runs against every script in the repo, and it's caught real, non-obvious issues — not
just style complaints. One worth knowing: a helper function in `bin/e2e.sh` used to be written as

```bash
kx() { docker exec kafka /opt/kafka/bin/"$@"; }
```

This relies on a genuinely obscure bash quirk: when you write `prefix"$@"`, the prefix attaches only
to the *first* expanded word, not to all of them. For this project's specific call sites — always
`kx kafka-topics.sh --bootstrap-server ...` — that quirk happened to produce the right result. It
was still flagged as an error (SC2145), because the correctness depended entirely on every future
caller happening to pass arguments in exactly the same shape, with nothing in the syntax itself
making that requirement obvious. The fix makes the intent explicit instead of relying on the quirk:

```bash
kx() { local bin="$1"; shift; docker exec kafka "/opt/kafka/bin/$bin" "$@"; }
```

## A test that proves it actually tests something

`api/test/metrics.test.ts` guards against a real, previously-shipped bug: an earlier `/metrics`
implementation kept every request duration in an unbounded array and gave every distinct URL —
including 404s to scanned or mistyped paths — its own label. Under load that grew into a 7.5 MB
response across more than 90,000 time series.

Writing a test that asserts "the response is small" is easy. Writing a test that actually
*discriminates* — that would fail against the bug it claims to catch — is a different, stronger
bar, and it's worth checking directly rather than assuming:

```bash
cd api
cp src/plugins/metrics.ts /tmp/metrics-fixed.ts   # keep the current one safe
git show HEAD~N:src/plugins/metrics.ts > src/plugins/metrics.ts   # swap in the old hand-rolled version, if you have it
npx tsx --test test/metrics.test.ts
cp /tmp/metrics-fixed.ts src/plugins/metrics.ts    # restore
```

Run against the genuinely broken implementation, three of the four tests fail — the exact three
that test cardinality, response size, and real histogram buckets. The fourth, unrelated to the bug
(it only checks the `Content-Type` header), correctly still passes. That asymmetry is what makes it
a real regression test rather than one that would pass on anything.

## The GitOps hand-off

The piece Chapter 11 depends on lives in `build-and-push`, after the image itself is pushed:

```yaml
- run: kustomize edit set image "$IMAGE=$IMAGE:${{ steps.sha.outputs.short }}"
  working-directory: k8s
- run: git commit -m "k8s: bump adlab-api image to sha-... [skip ci]" && git push
```

This is what turns "a new image exists in GHCR" into "the cluster is told to run it" — without it,
`kustomization.yaml` would sit forever referencing `:latest`, and ArgoCD would have no way to know a
new build even happened. `git log --oneline -- k8s/kustomization.yaml` is the fastest way to confirm
this step is actually firing; every commit there authored by `github-actions[bot]` is one successful
loop.

## Branch protection: the last piece

None of the above stops an unreviewed change from reaching `main` on its own — CI checks passing and
a PR being *mergeable* are two separate settings. `.github/CODEOWNERS`, paired with **Require review
from Code Owners** in the repository's branch protection rule, makes a named reviewer mandatory on
every pull request regardless of who else approves. Pairing it with **Require status checks to pass
before merging**, pointed at the three unconditional jobs from `ci.yml` (never the path-filtered
build jobs, which wouldn't run at all on a docs-only PR and would block it forever if required), is
what actually closes the loop this whole chapter has been describing: nothing reaches `main` without
both a human and the automation agreeing.

## What's next

Chapter 13 is the capstone — a real bug, deliberately reintroduced into a copy of this project, with
no chapter number attached to tell you where to look.
