# Working in this repository

This is the OSO Organised marketing website, a static site served by GitHub
Pages from `/docs` on `main`. Lucy (the founder, not a developer) is the
repository owner.

## Rules for any Claude Code session working here

- **Never push directly to `main`.** Always create a new branch, make the
  change, commit, push the branch, and open a pull request.
- **Never merge your own pull request.** Open it and ask Lucy to review and
  merge it herself.
- **Write the PR description in plain English** for a non-technical reader:
  say what changed, in everyday terms, not just file paths.
- **If the change touches links, forms, or any code that connects to the
  OSO Organised app**, say so explicitly and clearly near the top of the PR
  description, so it's easy to spot.
- The one exception is `/docs/app-connect/`: Alex can work in that folder
  more freely, but the branch-and-pull-request workflow above still
  applies, it just does not require Lucy's review to merge (see
  `.github/CODEOWNERS`).
