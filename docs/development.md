# Development and verification

Install Python 3.9+, Go 1.27.4 or newer, Java 21, Git, Bash 4+, curl and jq. Go must already be available on `PATH`; preparation uses `GOTOOLCHAIN=local`. The pinned Gradle wrapper requires network access on first use. The Linux runtime also needs Bash, curl, jq, sha256sum and base64 from the foundation's compatible Agent Buildpack/stack.

```sh
bin/prepare
bin/prepare --check
bin/verify
```

Preparation downloads the official oauth2-proxy Linux/amd64 release and checks both archive and executable hashes. It builds the Market JAR and the guide/relay binaries from the exact trees in `provenance/dependencies.json`, then writes ignored `.artifacts/prepare-state.json`. Any source change requires deliberately updating that component's `source.tree_sha256` and preparing again. The digest recipe is the existing `source_tree_sha256` function in `bin/prepare`; it excludes generated build/cache directories.

`bin/verify --static` checks local documentation links, source/archive pins, JSON/Python/shell syntax, and native topology/manifest closure. Full verification also checks prepared outputs, runs the retained Python orchestration and launcher regressions, both Go suites, and the Market integration suite. It never logs into CF, creates an OAuth client, or invokes a model. A fresh clone must pass without private repositories or credentials.

`bin/prepare --offline DIRECTORY` accepts the pinned oauth2-proxy archive from an operator-provided directory. It also requires populated Gradle caches and the toolchains already installed. Set `GRADLE_USER_HOME="$PWD/.artifacts/gradle-home"` for both preparation and verification when sharing an offline cache; otherwise Gradle preparation uses its normal user cache while verification defaults to the kit cache. This option does not claim network isolation. Runtime model, identity and optional Hub endpoints are online services.

## Local browser preview

```sh
cd apps/demo-guide
go run . --preview
```

The preview serves only on `127.0.0.1:8766`, is refused inside CF, and is synthetic UI verification. Set non-secret `GUIDE_*` environment variables for representative links. A preview does not test SSO or platform integrations.

For Market, run `./gradlew bootRun` in `apps/market` and open `http://localhost:8080`. It uses an in-memory database and synthetic catalog by default. Run its existing integration tests after changes to APIs, MCP, security or persistence.

## Security maintenance

Use maintained tools such as Gitleaks for Git/source secrets and Trivy's `rootfs --scanners vuln` for prepared JARs and Go executables. The `fs` analyzer alone may not inventory those binaries. Record artifact hashes, scanner/database dates and vendor applicability; package matches do not by themselves prove exploitability. Upgrade official dependencies and rerun the affected flows. Do not suppress findings just to make CI green.

The public candidate's actual checks and limitations are recorded in [verification](verification.md). CI does not deploy or use foundation credentials. Dependency update configuration covers Gradle, Go and GitHub Actions; oauth2-proxy's release/hash ledger requires an explicit reviewed update.

Dependency-update pull requests that change a source tree also require updating its deliberate `tree_sha256` pin and preparing again; CI will fail until those reviewed changes agree. Dependabot does not update this project-specific ledger automatically.
