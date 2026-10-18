# CHANGELOG

<!-- version list -->

## v0.3.0 (2026-10-18)

### Bug Fixes

- Correct power sizing, degenerate inputs and concurrent calls
  ([`3646783`](http://localhost:3000/jmbr/askance/commit/3646783ff63ed57f967786621ea570084d8dc6c4))

### Build System

- Cut versions from the commit history
  ([`f80f24d`](http://localhost:3000/jmbr/askance/commit/f80f24ddcde0ebc85862328d13217a8c3d35bbf2))

### Documentation

- Make the install steps work on a fresh machine
  ([`9efa7fd`](http://localhost:3000/jmbr/askance/commit/9efa7fd929daf1a143471bda0580a2d2e914c9bb))

- Point the skill at git.superadditive.com
  ([`b652180`](http://localhost:3000/jmbr/askance/commit/b652180b0d593c5a9ff35c80db517febde28c414))

- Say which commits cut a release
  ([`4637fb3`](http://localhost:3000/jmbr/askance/commit/4637fb306c29fd40494808c6163c712dfe2afbeb))

- Split the readme by reader
  ([`6fe0728`](http://localhost:3000/jmbr/askance/commit/6fe0728d391f9b95b14921e9ae061df1c0b9cfde))

- Tighten prose and remove redundant comments
  ([`54d1543`](http://localhost:3000/jmbr/askance/commit/54d1543c4c867632f26efa26b5cc5a94d7872d5f))

- Update installation instructions.
  ([`9f7cff1`](http://localhost:3000/jmbr/askance/commit/9f7cff10c4647ad6b6a3c14cb050c77552ff0dc4))

### Testing

- Deliver skill eval prompts to the agent intact
  ([`d692c92`](http://localhost:3000/jmbr/askance/commit/d692c928f3ad6285648303197b4b8e1f4875acab))

- Keep the release configuration honest
  ([`58fc0ce`](http://localhost:3000/jmbr/askance/commit/58fc0ced0bace1902b4905c33cfb01b413a3cd7d))

### Breaking Changes

- The chi_square power design takes rows and columns instead of groups; MCP tools refuse booleans,
  numeric strings and whole-number floats that they used to coerce; one_way_anova, kruskal_wallis
  and pearson_correlation results no longer include degrees_of_freedom; and a solved one_way_anova n
  is rounded up to a multiple of groups.


## v0.2.0 (2026-09-21)

- Initial Release
