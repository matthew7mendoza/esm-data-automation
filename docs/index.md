# ESM Tracker Quickstart

Welcome to the ESM Tracker documentation. This tool automates the process of scanning your climate model output data and sending the metadata to the central dashboard for documentation.

## Installation

You can install the tool directly into your Conda environment. Run this single command on the terminal:

```bash
conda install -c matthew7mendoza esm-tracker
```

## First Setup

Before running the tracker, you need to securely connect it to the web dashboard. 

1. Go to the web dashboard and generate a secure token.
2. In your terminal, run:

```bash
esm-tracker init --experiment "My First Run" --model "GFDL SPEAR" --token "YOUR_TOKEN_HERE" --publish
```

This command will:

* Save your token securely.
* Scan your current folder.
* Send the required metadata to the server.

You are now ready to track your data!
