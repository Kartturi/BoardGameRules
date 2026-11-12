# Task 13: GCP Cloud Run CD Deployment Pipeline

## Objective
Create a GitHub Actions Continuous Deployment (CD) workflow to build Docker images, push them to Google Artifact Registry, and deploy to GCP Cloud Run Services & Jobs.

## Requirements
- Create `.github/workflows/deploy-gcp.yml` to build and push backend, frontend, and batch worker images to Google Artifact Registry.
- Deploy containers to GCP Cloud Run Services and Cloud Run Jobs.
- Configure keyless authentication using GCP Workload Identity Federation (OIDC) instead of static service account keys.
- Document required GitHub secrets/variables and GCP IAM setup commands.
