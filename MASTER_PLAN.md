# The Master Plan: ESM Data Compliance Automation

## Part 1: The Motivation (Why I Am Pivoting)
When this project started, the goal was to automate the generation of Data Management Plans (DMPs), READMEs, and Draft DOIs for Earth System Model outputs. The initial system allowed a scientist to open a Streamlit web app, upload files, and rely on an LLM to read the documents and fill out compliance forms.

However, a critical realization occurred: relying on AI to "guess" physical data bounds, variables, and temporal ranges from PDFs is dangerous and prone to hallucination. Furthermore, requiring scientists to manually move terabytes of NetCDF and Zarr files from the supercomputer (PPAN) to a web browser is impossible.

The new philosophy: Use deterministic Python (`xarray`) to extract the mathematical truth, and use the LLM strictly as a translator/synthesizer on top of that verified truth. The goal is to build a frictionless, enterprise-grade data compliance engine that seamlessly integrates into the daily workflow of a research scientist.

## Part 2: What I Have So Far (The Strangler Fig Pattern)
The existing work is not being thrown away. The current Streamlit app (`esm-data-automation`) will be restructured using the "Strangler Fig Pattern." The Landing Page will now feature a "Fork in the Road" with two distinct pathways:

* **Card A: Start a New Experiment (Metadata Tracker):** The new pivot. A Day Zero Onboarding Hub that sets up automated metadata tracking for a new or ongoing model run on PPAN.
* **Card B: Retroactive Form Automation (The Typer):** The legacy tool. Designed for scientists who already have an old folder of PDFs/data and just want the LLM to instantly generate their compliance forms.

## Part 3: My Ultimate Goal
The ultimate goal is to treat data management exactly like software code (GitOps). This system will act as an Automated Guardian Angel—a system that automatically maps a massive workspace, mathematically extracts exact data variables, standardizes them, writes the DMP and README using AI, verifies the science via image-auditing, and prepares the Princeton Draft DOI.

## Part 4: The Architecture (The Organization)
To ensure this scales across the lab, regardless of whether scientists use Git/GitHub or not, the infrastructure is split into three decoupled layers:

1. **The Brain (`esm-model-registry`):** A public repository holding highly decoupled YAML files that define model archetypes (e.g., GFDL SPEAR). This is the source of truth for all standardized CMIP6 variables. If a standard name updates here, the entire system adapts.
2. **The Bootstrapper (`esm-data-automation`):** The Streamlit app. Scientists visit this hub to register their experiment, generate a secure API token, and retrieve the specific commands they need to run on the supercomputer terminal.
3. **The Scanner CLI (`esm-tracker`):** A professional, highly-optimized Python package deployed directly to the Anaconda Cloud and PyPI. Instead of relying on invisible Git hooks, scientists seamlessly pull the tool natively into their PPAN environments (`conda install -c matthew7mendoza esm-tracker` or `pip install esm-tracker`). 

## Part 5: The Execution Pipeline (How It Actually Works)

### Step 1: Day Zero (The Setup)
A scientist starts a project. They use Card A in the Streamlit app to register their experiment. The app generates a secure API token and a single, frictionless command to run on their supercomputer terminal (e.g., `conda install -c matthew7mendoza esm-tracker` or `pip install esm-tracker`).

### Step 2: The Project Scanner (esm-tracker)
The scientist runs the CLI command in their PPAN workspace (`esm-tracker init`). The tracker recursively scans the directory for `.nc` and `.zarr` files using deterministic Python (`xarray`). To handle massive HPC workloads, it natively features:
* **Multiprocessing**: Parallelizing extraction across CPU cores.
* **Incremental Caching**: Only scanning newly modified files.
* **SLURM Integration**: Automatically generating `sbatch` scripts to offload parsing to compute nodes.
* **Regex Filtering**: Instantly ignoring irrelevant outputs (e.g., restarts).

### Step 3: The `project_summary.yaml`
The scanner condenses mathematically verified facts from terabytes of data into a tiny, lightweight text file called `project_summary.yaml`. This file is the absolute ground-truth receipt of their project, containing file sizes, dimensions, variables, and global attributes. 

### Step 4: The Hybrid Bridge (AI Synthesis without Hallucinations)
Because not all scientists use GitHub, there are three paths for AI synthesis:
* **Path A (Zero-Setup CLI Publish):** The scientist passes the `--publish` flag directly in their terminal along with their secure `--token`. `esm-tracker` beams the condensed metadata payload and custom templates straight to the web API, generating the DMP/README dynamically.
* **Path B (Manual UI):** The scientist drags and drops their `project_summary.yaml` back into the Streamlit app manually. 
* **Path C (GitOps):** The CLI tool pushes the `project_summary.yaml` to a GitHub repository, waking up a GitHub Action that spins up a VM, runs the AI synthesis, and opens an automated Pull Request with the forms.

### Step 5: The Autonomous QC Oracle & DOI Minting
Before finalizing, diagnostic anomaly plots (PNGs) can be fed to the Gemini Vision API to audit contours and axes for physical corruption. Once the scientist reviews and approves the paperwork (Human-in-the-Loop), a webhook fires the final metadata payload to the Princeton Research Data Service (PRDS) to reserve the Draft DOI.

### Step 6: The Time Machine (Undo & Version Control)
If a scientist realizes an upstream model run was flawed or the wrong directory was scanned, they can seamlessly update their project using the `esm-tracker run --force-update` command. 
* **Project ID (UUID):** Projects are tracked via a hidden unique identifier generated on Day Zero, guaranteeing updates map to the correct project regardless of folder renames.
* **The "Pull Request" Diff View:** The backend places the update in a "Pending Review" state. In the Streamlit app, the scientist is presented with a side-by-side visual diff of the metadata changes.
* **Version Ledger:** The system stores an immutable history of `project_summary.yaml` payloads (v1, v2, etc.), allowing the scientist to revert to a previous state instantly.
* **Approval & Regeneration:** The AI only regenerates the compliance forms and Draft DOI mapping document once the scientist manually clicks "Approve Overwrite".

## Part 6: Expanding Horizons (The Data Mesh)
Because every project will now output a standardized `project_summary.yaml`, this infrastructure lays the groundwork for:
* **An Institutional Search Engine:** A crawler that aggregates every summary across the lab, allowing researchers to instantly query who ran what variables, and exactly where the data lives on the HPC.
* **Live Dashboards:** Automatically publishing AI-audited QC plots to GitHub Pages.
* **Automated Storage Auditing:** Tracking total file sizes generated on PPAN to identify "zombie" runs for tape-storage archival.

## Part 7: The Baby Steps Action Plan
To execute this seamlessly, development is proceeding in modular stages:

* [x] **The Scanner Script (esm-tracker):** Write a strict, PEP-compliant scanner module (`scanner.py`) supporting both NetCDF and Zarr. Implement aggressive optimizations (Multiprocessing, SLURM, Incremental Caching, Regex filtering). **(COMPLETED)**
* [x] **CLI Packaging & Cloud Publishing:** Package the scanner into a professional CLI tool and deploy it seamlessly to the Anaconda Cloud and PyPI for frictionless installation anywhere. **(COMPLETED)**
* [x] **The UI Fork & Authentication:** Update the Streamlit app to feature the two pathways (Card A / Card B) and build a secure, stateless API token generator to lock down the backend against unauthorized CLI payloads. **(COMPLETED)**
* [x] **The Streamlit Ingestion:** Ensure the FastAPI backend / Streamlit frontend seamlessly accepts the published payloads from the CLI and writes the DMP/README directly from its verified facts. **(COMPLETED)**
* [x] **The Time Machine (Undo & Version Control):** Implement the `esm-tracker run --force-update` mechanism, strict UUID data isolation in the FastAPI backend, and the GitHub-style visual diff human-in-the-loop approval workflow in the Streamlit frontend. **(COMPLETED)**
* [x] **Documentation & User Onboarding:** Write the official `esm-tracker` documentation (e.g., using MkDocs or Sphinx) that clearly explains the regex filtering rules, how the SLURM offloading works, and exactly what data is (and isn't) sent to the external API. **(COMPLETED)**
