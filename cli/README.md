# ESM Data Automation: How to Use This Program

This tool helps scientists automatically generate compliance forms (like Data Management Plans and READMEs) for large climate datasets directly within their remote or local compute environments. It does this without requiring you to move terabytes of data manually.

## Step 1: Get Your Secure Token from the Web App
1. Open the ESM Data Automation Web Application in your browser.
2. Click on **Initialize Automated Data Tracking (CLI)**.
3. Select your model (e.g., GFDL SPEAR) and enter a name for your experiment.
4. Click **Generate Setup Command**. The web app will give you a secure API token and a terminal command to copy.

## Step 2: Scan Your Data in the Terminal
1. Open the terminal for your compute environment and navigate to the folder containing your data.
2. Install the scanner tool:
   ```bash
   conda install -c matthew7mendoza esm-tracker
   ```
3. Paste the command you copied from the web app, and add the `--publish` flag to the end of it:
   ```bash
   esm-tracker init --experiment "my_run" --model "GFDL SPEAR" --token "YOUR_TOKEN" --publish
   ```
4. *Tip:* Add `--slurm` to the end of the command if you want it to run in the background on a compute node (if your cluster uses the SLURM scheduler).
5. The tool will scan all your `.nc` (NetCDF) and `.zarr` files. If any files are corrupted or stuck on tape storage, it safely logs the error and continues scanning without crashing.

## Step 3: Review Your Automated Documents
1. Because you used the `--publish` flag, the scanner will automatically send the final summary of your data (`project_summary.yaml`) back to the web application.
2. Your terminal will print a clickable web link. Click it!
3. The web application will load, and the AI will have automatically written your Data Management Plan or README using the verified measurements from your compute environment.
4. Review the document, make any necessary edits in the web interface, and download it.

*(Note: If you already have your metadata summaries or PDFs and just want to generate a form manually, you can skip the CLI entirely. Just click **Process Existing Manual Documents** on the web app homepage and upload your files directly.)*

---

## Exhaustive Command List

Here is every single command you can use with `esm-tracker` if you want to customize your scan.

### `esm-tracker init`
This is the main command that starts the scanning process.

**Required:**
* `--experiment`: The name of your experiment. (Example: `--experiment "my_run_01"`)
* `--model`: The name of the climate model you used. (Example: `--model "GFDL SPEAR"`)

**Optional:**
* `--directory`: The folder you want to scan. Defaults to the folder you are currently inside.
* `--include`: Only scan files that match this specific pattern. (Example: `--include "*_monthly.nc"`)
* `--exclude`: Completely skip files that match this pattern. (Example: `--exclude "*restart*"`)
* `--watch`: Run forever in the background. It will automatically update your summary the exact moment a new file appears in your folder.
* `--slurm`: Automatically submit this scan as a background job to a SLURM scheduler.
* `--publish`: After it finishes scanning, automatically send the summary to the web application.
* `--template`: If you use `--publish`, this tells the AI what kind of document to make. Defaults to a "DMP". (Example: `--template "README"`)
* `--prompt-file`: A normal text file containing special instructions for the AI to read. (Example: `--prompt-file my_rules.txt`)
* `--provider`: The AI company you want to use. Defaults to "gemini". (Example: `--provider "openai"`)

### `esm-tracker config`
This command is used to save your personal AI keys securely in the system if you are running a custom backend.

* `--api-key`: Your secret key. (Example: `--api-key "sk-12345"`)
* `--provider`: The company the key belongs to. (Example: `--provider "openai"`)
* `--name`: A nickname for this key. (Example: `--name "my-work-key"`)
