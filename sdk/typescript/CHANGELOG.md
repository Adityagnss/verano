# Changelog

Semantic versioning; the version is in `package.json` and `VERSION` in `src/index.ts`. Releases are tagged
`sdk-ts-vX.Y.Z`.

## 0.1.0 (unreleased)

- First version: `new Verano().prompt(name, { label })`, ETag revalidation, a memory and disk cache, a fallback to the
  last good copy when Verano is unreachable (`fromCache`, `onFallback`), `render`.
