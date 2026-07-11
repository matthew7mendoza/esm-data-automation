# Intern Testing Guide: esm-tracker CLI

Welcome! This guide explains how to install and test the experimental `esm-tracker` CLI tool on the NOAA GFDL PPAN cluster. 

The tool has been published to a temporary development channel on Anaconda Cloud, so you can install it exactly as you would any other production package.

---

## 1. Connect to PPAN and Activate your Environment

Log into the PPAN cluster and activate the Conda environment you want to use for testing. (If you do not have one, you can create a fresh one).

```bash
ssh <your_username>@ppan.gfdl.noaa.gov
module load conda
conda activate your_existing_environment
```

## 2. Install the Tracker

Install the `esm-tracker` directly from our development Anaconda channel. 



```bash
conda install -c matthew7mendoza esm-tracker
```

## 3. Test the Tool

The CLI is now fully installed on your system. You can point it at any of your NetCDF or Zarr data directories to extract the metadata and publish it to the backend.

```bash
esm-tracker init \
  --experiment "intern_test_01" \
  --model "GFDL SPEAR" \
  --directory /work/$USER/path/to/test/data \
  --publish
```

If it works as expected, let the lead developer know! If you ever want to remove the tool from your environment, simply run:
```bash
conda remove esm-tracker
```
