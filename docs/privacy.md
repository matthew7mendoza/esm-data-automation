# Data Privacy & Security

As a scientist, your raw data is your most valuable asset. 

**The Golden Rule:** No raw scientific data, arrays, or numbers ever leave the supercomputer. 

The `esm-tracker` tool strictly reads the **metadata** (the labels and sizes of your data) and completely ignores the actual numbers.

## What exactly is sent?

When you run the tool with the `--publish` flag, it generates a tiny text file called `project_summary.yaml` and sends that to the server.

Here is an example of what that payload looks like:

```yaml
project_unique_identifier: "abc-123-def"
is_force_update_boolean: false
experiment_name: "My Run"
model_archetype: "GFDL"
datasets:
  - file_name: "ocean_monthly.nc"
    file_size_bytes: 104857600
    status: "ok"
    variables:
      - "temperature"
      - "salinity"
    dimensions:
      time: 12
      lat: 180
      lon: 360
    global_attributes:
      history: "Created on 2026-07-11"
```

As you can see, only file names, variables, and dimensions are sent. Your science is completely safe.
