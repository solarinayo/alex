# Alex on GCP (Tolu-style stack)

This directory mirrors the layout used in [Toluwalemi/andela-alex-project](https://github.com/Toluwalemi/andela-alex-project): **Cloud Run** (FastAPI + Next.js), **Cloud SQL** (PostgreSQL), **Cloud Storage**, **Secret Manager**, **Artifact Registry**, and **Workload Identity Federation** for GitHub Actions.

It does **not** replace the course’s AWS modules (`2_sagemaker` … `8_enterprise`). Those stay for the Udemy path. Use this folder when you want GCP instead.

## Prerequisites

- A GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login` for Terraform)
- APIs enabled via Terraform on first apply

## Configure

```bash
cd terraform/gcp
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: project_id, github_repo, Clerk URLs
```

`github_repo` must match the GitHub `owner/name` string exactly (used in WIF `attribute_condition`).

### OpenAI API key (keep it out of `terraform.tfvars`)

`terraform/gcp/terraform.tfvars` is listed in **`.gitignore`** (`*.tfvars` is not committed), but you should still **avoid pasting long-lived API keys** into that file in case the file is copied, screenshared, or synced to another machine.

Set the key only for the shell session Terraform uses:

```bash
export TF_VAR_openai_api_key="sk-..."   # or paste once from 1Password / a password manager
```

Then run `terraform plan` and `terraform apply` in the **same terminal**.

If a key was ever **committed, pushed, or pasted in chat**, **rotate** it: [OpenAI API keys](https://platform.openai.com/api-keys) → revoke the old key → set `TF_VAR_openai_api_key` to the new key, then if Terraform must update the Secret Manager value, run `apply` again.

**Update the key in GCP only** (no Terraform), if you prefer:

```bash
printf '%s' 'sk-...' | gcloud secrets versions add alex-api-openai-api-key --data-file=- --project=YOUR_PROJECT_ID
```

(Replace `alex-api-openai-api-key` if you changed `backend_service_name` in variables.)

## Apply

```bash
# After: export TF_VAR_openai_api_key=...
terraform init
terraform plan
terraform apply
```

After apply, push real container images to Artifact Registry and deploy to the existing Cloud Run services (the Terraform `lifecycle.ignore_changes` on `image` is intentional so CI can update images).

## Your service URLs (after apply)

```bash
cd terraform/gcp
terraform output
```

Use **`backend_service_url`** and **`frontend_service_url`** in the browser. Example shape: `https://alex-api-XXXX-ew.a.run.app` and `https://alex-web-XXXX-ew.a.run.app`.

## GitHub Actions (CI → Artifact Registry → Cloud Run)

The workflow is **`.github/workflows/deploy-gcp.yml`**. It builds `backend/Dockerfile.gcp` and `frontend/Dockerfile.gcp`, pushes to Artifact Registry, and runs `gcloud run services update` for `alex-api` and `alex-web`.

### Repository settings (GitHub → *your repo* → Settings)

**Secrets (Sensitive)**

| Name | Value |
|------|--------|
| `WIF_PROVIDER` | `terraform output -raw wif_provider` (long name like `projects/123/.../providers/github-provider`) |
| `GCP_SERVICE_ACCOUNT` | `terraform output -raw app_deployer_service_account` (e.g. `gh-alex-app-deployer@....iam.gserviceaccount.com`) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk “Publishable key” (`pk_test_...` / `pk_live_...`) for the static frontend build |

**Variables (not necessarily secret)**

| Name | Example |
|------|--------|
| `GCP_PROJECT_ID` | `jekacode-488803` (your project id) |
| `NEXT_PUBLIC_API_URL` | Full `backend_service_url` from Terraform, e.g. `https://alex-api-xxxxx-ew.a.run.app` (used at Next build time) |

`terraform.tfvars` **`github_repo`** must equal this repository as `owner/name` (e.g. `solarinayo/alex`), or the OIDC token from Actions will not match the Workload Identity pool and auth will fail.

#### Step by step: get each value

**Part A — From your computer (Terraform already applied once)**

1. Open Terminal.
2. In Terminal, **change directory** to this folder (the words `terraform/gcp` in docs mean “this path”, not something you type as a command):

   ```bash
   cd "/Users/solarinayomide/Desktop/all/Andela - Ai Engineering/alex/terraform/gcp"
   ```

3. If typing `terraform` says **command not found**, your binary is in `~/bin` from the manual install. Use the **full path** for every Terraform command, for example `"$HOME/bin/terraform"`, or add to `~/.zshrc` once: `export PATH="$HOME/bin:$PATH"` and open a new terminal.

4. **Secret `WIF_PROVIDER`** — run, then copy the **entire** single line of output (no extra spaces or line breaks). If `terraform` is not on your `PATH`, use the same path you used when `terraform` worked (for example `~/bin/terraform`):

   ```bash
   "$HOME/bin/terraform" output -raw wif_provider
   ```

   Expected shape: `projects/NUMBERS/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider`

5. **Secret `GCP_SERVICE_ACCOUNT`** — run, then copy the email:

   ```bash
   "$HOME/bin/terraform" output -raw app_deployer_service_account
   ```

   Expected shape: `gh-alex-app-deployer@YOUR-PROJECT-ID.iam.gserviceaccount.com`

6. **Variable `NEXT_PUBLIC_API_URL`** — run, then copy the URL (this is the API the browser will call):

   ```bash
   "$HOME/bin/terraform" output -raw backend_service_url
   ```

   Expected shape: `https://alex-api-??????-ew.a.run.app`

7. **Variable `GCP_PROJECT_ID`** — open your local `terraform/gcp/terraform.tfvars` and copy the value in quotes after `project_id` (e.g. `jekacode-488803`). That file is not committed; it is only on your machine.

**Part B — From Clerk (browser)**

1. Go to [https://dashboard.clerk.com](https://dashboard.clerk.com) and open your app.
2. **Configure** → **API keys** (wording can vary).
3. Copy the **Publishable key** (starts with `pk_test_` or `pk_live_`). That is **Secret `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`**.

**Part C — Paste into GitHub**

1. Open: [https://github.com/solarinayo/alex/settings/secrets/actions](https://github.com/solarinayo/alex/settings/secrets/actions) (you must be logged in as a repo **admin**).
2. **Secrets** tab → **New repository secret** three times:

   | Name | Paste |
   |------|--------|
   | `WIF_PROVIDER` | Output of `terraform output -raw wif_provider` |
   | `GCP_SERVICE_ACCOUNT` | Output of `terraform output -raw app_deployer_service_account` |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_...` from Clerk |

3. **Variables** tab (same page) → **New repository variable** twice:

   | Name | Value |
   |------|--------|
   | `GCP_PROJECT_ID` | e.g. `jekacode-488803` |
   | `NEXT_PUBLIC_API_URL` | Output of `terraform output -raw backend_service_url` (full `https://...` URL, no trailing `/`) |

4. **Actions** → **Deploy GCP (Cloud Run)** → open the last run → **Re-run all jobs** (or push a commit to `main`).

### Run the workflow

- Push to **`main`**, or use **Actions → Deploy GCP (Cloud Run) → Run workflow**.

**Course API note:** `backend/api` still opens **Aurora via boto3** at import. A deploy may succeed while the service logs show DB connection errors until you point `alex-database` at **Cloud SQL** and adjust env/config. The workflow still proves **Terraform + WIF + CI** for the “Alex agentic” criteria; finishing the data layer is the next coding step.

## Application work still required

Course `backend/api` is built for **Lambda + Mangum + Aurora Data API + boto3**. Tolu’s backend is a **single FastAPI** app using **Cloud SQL** (often via `/cloudsql/INSTANCE` or the Cloud SQL Auth Proxy) and a hosted LLM API. This GCP stack wires **OpenAI** (`OPENAI_API_KEY`, `OPENAI_MODEL`) plus Clerk and DB env vars on Cloud Run. Porting this repo means:

- Using the OpenAI SDK (or LiteLLM with `openai/...`) in your FastAPI code, reading `OPENAI_API_KEY` / `OPENAI_MODEL`
- Swapping the database client from RDS Data API to PostgreSQL over Cloud SQL
- Containerizing `backend/api` and the Next.js `frontend` with Dockerfiles that match Cloud Run ports (8000 / 3000)
- Pointing the frontend at the Cloud Run API URL

Env vars set on the backend service: `INSTANCE_CONNECTION_NAME`, `DB_*`, `OPENAI_*`, `CLERK_*`, `GCS_BUCKET_NAME`.
