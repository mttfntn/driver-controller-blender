# Contributing to Driver Controller

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or suggesting a feature

Open an [issue](https://github.com/mttfntn/driver-controller-blender/issues/new/choose) and pick a form:

- **Bug report:** say which Blender version and add-on version you use, and the steps to reproduce. A small `.blend` file helps most.
- **Feature request:** describe what you're trying to do, not only the solution you have in mind.

First, check whether someone has already opened an issue for the same thing.

## Changing the code

[HANDOVER.md](HANDOVER.md) explains how the add-on is organised and the pitfalls already found. Read it before a larger change.

1. **Fork** the repository and create a branch for your change.
2. You need **Blender 5.3** (the only supported version) and Python 3.
3. Run the tests. They start their own background Blender with a throw-away profile, so your Blender setup is never touched:

   ```
   python tests/run_blender.py
   ```

   Expected result: `Ran 41 tests ... OK` (or more). If Blender isn't found, add `--blender "path/to/blender"`.
4. **If you fix a bug,** add a test to `tests/test_addon.py` that fails without your fix.
5. **If your change could alter results,** compare behaviour with `main` using the probe tools (HANDOVER.md, "Making a change") and explain any difference in the pull request.
6. **Open a pull request.** The template has a short checklist. CI runs the tests, builds the extension and installs the built zip on Blender 5.3.

### Style

- The add-on is one module, `driver_controller/__init__.py`; its header lists the sections in order. Keep new code in the matching section.
- Give new helper functions a docstring that says what they do.
- **Operators and panels:** no docstrings, because Blender shows them as tooltips. Write the tooltip in `bl_description` and use `#` comments.
- Draw code must not change data.
- Keep commits small, with messages that explain what changed and how you checked it.

## License

Driver Controller is GPL-3.0-or-later. By contributing, you agree that your contribution is released under the same license.
