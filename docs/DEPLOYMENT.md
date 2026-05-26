# Docs Deployment Notes

These notes are for maintainers and are not part of the public Docusaurus docs.

The documentation site is a Docusaurus app inside the repository's `docs` folder.

## Local Development

```bash
cd docs
npm install
npm run start
```

## Production Build

```bash
cd docs
npm run build
```

Docusaurus writes static files to:

```text
docs/build
```

## Vercel

Import the GitHub repository into Vercel and use:

```text
Root Directory: docs
Build Command: npm run build
Output Directory: build
Install Command: npm install
```

Use this setup when the docs live in the same Git repository as the Python package.

## Suggested GitHub Workflow

Keep docs changes in the same pull request as code changes when possible:

```text
src/contextcrumb/...
docs/docs/...
README.md
CHANGELOG.md
```

This keeps public behavior, examples, and documentation in sync.
