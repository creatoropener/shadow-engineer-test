# shadow-engineer-test

Small fixture repository for the Shadow Engineer / PatchProof workflow.

## Prepare the Nebius Sandbox image

The `Prepare Sandbox Image` workflow supports either of these authentication modes:

1. Preferred IAM mode: set Actions secrets `NEBIUS_IAM_TOKEN` and
   `NEBIUS_PROJECT_ID`. The token and project must belong together, and the project
   must have access to the Nebius Sandboxes beta.
2. Legacy mode: set the organizer-provided `CONTREE_TOKEN`. Do not also set
   `NEBIUS_IAM_TOKEN` unless IAM mode is intended.

The OpenAI-compatible inference credential normally stored as `NEBIUS_API_KEY`
is used for model requests. It should not be assumed to have Sandbox permissions.
Never paste credentials into workflow files, logs, issues, or commits.

Run **Actions → Prepare Sandbox Image → Run workflow**. A successful run records
the immutable image UUID and tag in the job summary. Save the UUID as the
`CONTREE_IMAGE` repository secret for the PatchProof verification workflow.

If the preflight reports `403 Forbidden`, verify that the project ID matches the
IAM token and ask Nebius to enable Sandboxes for the project. Sandboxes are currently
documented as a beta capability.

The existing `Shadow Fix` workflow still applies a scripted repair and runs pytest
on the GitHub runner. Preparing this image does not by itself move that workflow to
Nebius or add NVIDIA model inference.
