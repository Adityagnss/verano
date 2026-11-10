# Packaging check (2026-11-10)

The three packages were built from the repository and installed into clean environments, nothing from the repository on the
path. **Nothing was published**: that needs your PyPI and npm accounts and a decision.

| Package | Built | Clean install | What ran |
|---|---|---|---|
| `verano-sdk` 0.1.0 (Python) | wheel and source archive (`uv build`) | a new Python 3.12 virtual environment, no dependencies | imported, `__version__` and the installed version agree, asking an unreachable server with nothing saved raised `VeranoUnreachable` |
| `verano` 0.2.0 (command line) | wheel and source archive (`uv build`) | a new Python 3.12 virtual environment, dependencies fetched | `verano --version` printed 0.2.0 and `verano --help` listed the commands |
| `@verano/sdk` 0.1.0 (TypeScript) | `tsc`, then `npm pack` (about 6 files: `dist`, README, CHANGELOG, LICENSE) | an empty folder, `npm install` of the tarball | imported as an ES module, `VERSION` printed 0.1.0, an unreachable server raised `VeranoUnreachable` |

A flaw found and fixed: the Python SDK's wheel declared `Typing :: Typed` but did not contain the `py.typed` marker, so type
checkers would have ignored its types. The marker is now in `sdk/python/src/verano_sdk/`.

Not checked: Windows, Python 3.10, 3.11, 3.13 and 3.14 (pending check 14), Node versions other than 22, Bun and Deno, and
install from a real registry.

## To publish (run by you, with your own tokens)

```bash
# Python SDK and command line (from a clean checkout of the release commit)
cd sdk/python && uv build && uv publish          # needs a PyPI token in UV_PUBLISH_TOKEN
cd cli        && uv build && uv publish
# TypeScript SDK
cd sdk/typescript && npm ci && npm run build && npm publish --access public   # needs `npm login`
```

Then, on a machine with no checkout: `uvx verano --version`, `pip install verano-sdk` and `npm install @verano/sdk`.
