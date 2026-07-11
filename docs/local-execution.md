# How It Works Locally

When you run `esm-tracker`, it does the heavy lifting for you directly on the supercomputer. 

## Regex Filtering Rules

The scanner does not waste time reading every single file. It is smart about what it looks for.

**What it scans:**

* NetCDF files (`*.nc`)
* Zarr files (`*.zarr`)

**What it ignores (by default):**

* Restart files (files with `restart` in the name)
* Hidden folders

This ensures that only the final scientific outputs are processed.

## SLURM Offloading

Scanning thousands of files can be slow and might crash the head node if you run it directly. 

To solve this, you can add the `--slurm` flag to your command. 

```bash
esm-tracker init --experiment "My Run" --model "GFDL" --slurm
```

When you use this flag, the tool will automatically write an `sbatch` script and submit the job to the cluster. This runs the scan on a powerful compute node in the background, keeping the head node safe and speeding up the process.
