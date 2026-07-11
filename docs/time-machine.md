# The Time Machine (Undo Features)

Mistakes happen. Sometimes you scan the wrong folder, or you realize a model run was flawed and you need to restart it.

The ESM Tracker has a built-in "Time Machine" that allows you to safely overwrite an existing project without losing track of your history.

## How to Force an Update

If you need to update a project that has already been published, use the `run` command with the `--force-update` flag:

```bash
esm-tracker run --experiment "My Run" --model "GFDL" --publish --force-update
```

## The Approval Process

When you force an update, the new metadata is sent to the server, but it does **not** instantly overwrite your old documents.

1. The new data is placed in a "Pending Review" state.
2. You must open the web dashboard.
3. You will see a visual, side-by-side comparison of what changed.
4. If everything looks correct, you click the **Approve Overwrite** button on the website.

This two-step process ensures you never accidentally delete good documentation.
