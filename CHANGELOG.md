# Changelog

## [0.3.2](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.3.1...planbook-cli-v0.3.2) (2026-09-04)


### Documentation

* drop the claim that edge findings were reported to Planbook ([#24](https://github.com/bryantclark/planbook-cli/issues/24)) ([084ea80](https://github.com/bryantclark/planbook-cli/commit/084ea80f8cead826ea789b215bdf51f53fac7bbb))

## [0.3.1](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.3.0...planbook-cli-v0.3.1) (2026-09-04)


### Bug Fixes

* confirm no-school deletes with --yes like every other cascade ([#20](https://github.com/bryantclark/planbook-cli/issues/20)) ([70cef45](https://github.com/bryantclark/planbook-cli/commit/70cef45aaa6247c3345f3657860805833390a2e3))
* let the publish job clone a private repo ([#18](https://github.com/bryantclark/planbook-cli/issues/18)) ([14d1b96](https://github.com/bryantclark/planbook-cli/commit/14d1b9687260cee7cea590b748e1e1df8c40f4f0))

## [0.3.0](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.2.2...planbook-cli-v0.3.0) (2026-08-31)


### ⚠ BREAKING CHANGES

* `planbook auth login` and `planbook auth browser` are gone.

### Features

* a versioned machine contract, and one seam for every write ([70bbcb3](https://github.com/bryantclark/planbook-cli/commit/70bbcb30abfcbe1cc7404666d4bab4ec37090149))
* add agent discovery skill ([c89a9a0](https://github.com/bryantclark/planbook-cli/commit/c89a9a04c9268f87eea40f59f24ec38f566f98a4))
* CRUD for classes, lessons, units, events, and todos ([4c187b9](https://github.com/bryantclark/planbook-cli/commit/4c187b9a3b2ff4fef897a4c2c0edd47f9368eedf))
* guided sign-in for auth import ([#6](https://github.com/bryantclark/planbook-cli/issues/6)) ([847491b](https://github.com/bryantclark/planbook-cli/commit/847491b4f5248f2c26f027bd8f61c430e72cff54))
* initial CLI with token auth and browser sign-in ([47877cf](https://github.com/bryantclark/planbook-cli/commit/47877cff63f7c969307748cbbbd76afb72597de4))
* lesson-event decoding and no-school day safeguard ([def1184](https://github.com/bryantclark/planbook-cli/commit/def11842cbad614da4e3627b30cd03d63ccf03b0))
* one-command install and optional PyPI publishing ([b83d85a](https://github.com/bryantclark/planbook-cli/commit/b83d85adf1bfe86c653a71fd8e18904fe1511da1))
* project `lessons get`, and add `--raw` beside it ([0cb9599](https://github.com/bryantclark/planbook-cli/commit/0cb9599b8814d9bbd3d3c27e4e6d77b3164ae7d3))
* return new ids from creates and add dry-run support ([566375f](https://github.com/bryantclark/planbook-cli/commit/566375f21ac67457b60f69ba4abc85a73a1d0d6f))
* standards, assignments, and file attachments ([2e3c3cc](https://github.com/bryantclark/planbook-cli/commit/2e3c3cc30b923619b6249f6ec25308516271fdbf))
* students, attendance, grades, and templates ([c4cf47d](https://github.com/bryantclark/planbook-cli/commit/c4cf47dc247dc83596e5516a5221c4e62f85aaf7))


### Bug Fixes

* a broken endpoint is not a sign-in problem ([aa191c2](https://github.com/bryantclark/planbook-cli/commit/aa191c297e6e8ce754ff5ad753df895578809bf7))
* data loss in updates, date validation, and identity claims ([e84b171](https://github.com/bryantclark/planbook-cli/commit/e84b1713ee38bb2034b8ff630469ff1016158f13))
* date normalization, bulk validation, and edge cases ([78d6030](https://github.com/bryantclark/planbook-cli/commit/78d6030cd43d67e6f6846c5dc9a7dde056df1d7e))
* install from PyPI now that the package is published ([#9](https://github.com/bryantclark/planbook-cli/issues/9)) ([78aed8e](https://github.com/bryantclark/planbook-cli/commit/78aed8ef0655601ed2fbe04fe3910d07cdee57dd))
* publish to PyPI from the release workflow, not a release trigger ([#4](https://github.com/bryantclark/planbook-cli/issues/4)) ([0f19a86](https://github.com/bryantclark/planbook-cli/commit/0f19a869e213ba769130965e98b6dacc83454e15))
* use the generic updater for the __init__ version file ([#2](https://github.com/bryantclark/planbook-cli/issues/2)) ([78d0d28](https://github.com/bryantclark/planbook-cli/commit/78d0d28e410475dcf46d67b6c0b00eb1ee166253))


### Documentation

* restructure to standard project shape, cut duplication ([#11](https://github.com/bryantclark/planbook-cli/issues/11)) ([d29b2d2](https://github.com/bryantclark/planbook-cli/commit/d29b2d2dc58b141873b052b3aad98260181234e4))
* rewrite the agent-facing docs around the new contract ([1e79778](https://github.com/bryantclark/planbook-cli/commit/1e79778851e759c9f298b28217e202a9262d1002))
* security policy, production-readiness plan, and one auth path ([#12](https://github.com/bryantclark/planbook-cli/issues/12)) ([2c2389f](https://github.com/bryantclark/planbook-cli/commit/2c2389f02581a65aa937cdea11dade02710bab16))

## [0.2.2](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.2.1...planbook-cli-v0.2.2) (2026-08-30)


### Bug Fixes

* install from PyPI now that the package is published ([#9](https://github.com/bryantclark/planbook-cli/issues/9)) ([7934007](https://github.com/bryantclark/planbook-cli/commit/7934007ee8e5c1aead34d79c3843b616d5f210c4))

## [0.2.1](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.2.0...planbook-cli-v0.2.1) (2026-08-30)


### Features

* guided sign-in for auth import ([#6](https://github.com/bryantclark/planbook-cli/issues/6)) ([906e37d](https://github.com/bryantclark/planbook-cli/commit/906e37d692316105edab3e659e147ab97a9f4f8f))


### Bug Fixes

* publish to PyPI from the release workflow, not a release trigger ([#4](https://github.com/bryantclark/planbook-cli/issues/4)) ([0673bc7](https://github.com/bryantclark/planbook-cli/commit/0673bc79736ed6aa5a0b041cb7b6ed830cbe1b5e))

## [0.2.0](https://github.com/bryantclark/planbook-cli/compare/planbook-cli-v0.1.0...planbook-cli-v0.2.0) (2026-08-30)


### Features

* one-command install and optional PyPI publishing ([a7caa99](https://github.com/bryantclark/planbook-cli/commit/a7caa99d4240e05005a4e1914cd1fe19c7d32381))


### Bug Fixes

* use the generic updater for the __init__ version file ([#2](https://github.com/bryantclark/planbook-cli/issues/2)) ([e0b84ed](https://github.com/bryantclark/planbook-cli/commit/e0b84ed864b16ed75a793a7bb79b12f878d2c5af))
