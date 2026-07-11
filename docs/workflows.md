# Integration Workflows

Not everyone works directly on the supercomputer terminal. The ESM Tracker is built to adapt to your specific workflow.

## 1. Python API (Jupyter Notebooks)

If you use Jupyter Notebooks (or Google Colab) to analyze your data, you do not need to use the command line at all. You can use the built-in Python module.

```python
from pathlib import Path
from esm_tracker.scanner import scan_directory

# Target the folder containing your data
folder_path = Path("/data/my_experiment")

# Extract the metadata natively in Python
extracted_metadata = scan_directory(target_directory_path=folder_path)

print(f"Found {len(extracted_metadata)} files!")
```

## 2. GitHub Actions 

If you use GitHub to store your model configurations, you can fully automate the tracker. Whenever you push a change to your repository, a GitHub Action can run the tracker for you.

*(Note: You can download a ready-to-use GitHub Action workflow file directly from the web dashboard during your onboarding!)*

Here is the standard template you would place in `.github/workflows/esm-tracker.yml`:

```yaml
name: Run ESM Tracker
on: [push]

jobs:
  track-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install ESM Tracker
        run: pip install esm-tracker
      - name: Run Scan and Publish
        run: esm-tracker init --experiment "GitHub Run" --model "GFDL" --publish
        env:
          ESM_TRACKER_API_URL: ${{ secrets.ESM_API_URL }}
```

## 3. GitLab CI

For institutional GitLab users, you can achieve the same automation by placing this in your `.gitlab-ci.yml` file:

```yaml
track-data:
  image: python:3.12
  script:
    - pip install esm-tracker
    - esm-tracker init --experiment "GitLab Run" --model "GFDL" --publish
```
