# Contributing to Sidero Omni + Talos + Proxmox starter kit

This starter kit is community-driven. Contributions of any kind are welcome.

## How to contribute

### Reporting issues

Found a bug or have a suggestion? [Open an issue](../../issues) with:

- A short, clear title
- A description of the problem or suggestion
- Versions of Omni, Talos, and Proxmox
- Steps to reproduce the issue
- The expected behavior and the actual behavior
- Relevant log excerpts, with secrets removed

### Suggesting enhancements

Have an idea to improve the starter kit? To suggest it:

1. Check whether a similar issue exists.
2. Open a new issue with the "enhancement" label.
3. Describe your use case and proposed solution.
4. Be open to discussion and feedback.

### Documentation improvements

Documentation contributions include:

- Fixing typos or unclear explanations
- Adding examples or clarifications
- Improving troubleshooting guides
- Translating documentation
- Adding diagrams or illustrations

### Code contributions

#### Setting up development environment

1. Fork the repository.
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/sidero-omni-talos-proxmox-starter.git
   cd sidero-omni-talos-proxmox-starter
   ```
3. Create a branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

#### Making changes

For documentation:
- Use clear, short sentences
- Include code examples where helpful
- Test commands and configurations
- Update table of contents if adding sections

For configuration files:
- Use `.example` suffix for templates
- Include inline comments explaining options
- Provide defaults that work
- Document any required vs optional fields

For scripts:
- Add error handling
- Include usage instructions
- Use descriptive variable names
- Add comments for complex logic

#### Testing your changes

Before you submit:

1. Test configurations:
   - Verify example files have correct syntax
   - Test any scripts you've added or modified
   - Confirm commands work as documented

2. Check documentation:
   - Proofread for typos and clarity
   - Verify links work
   - Test code blocks in a clean environment

3. Validate against .gitignore:
   - Confirm you did not commit secrets
   - Check that example files are included

#### Submitting a pull request

1. Commit your changes:
   ```bash
   git add .
   git commit -m "feat: add support for X" # or "fix:", "docs:", etc.
   ```

2. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

3. Open a pull request:
   - Go to the original repository
   - Click "New Pull Request"
   - Select your branch
   - Fill out the PR template

4. Follow the PR guidelines:
   - Title: use conventional commit format
     - `feat:` for new features
     - `fix:` for bug fixes
     - `docs:` for documentation
     - `chore:` for maintenance
   - Description: explain what and why
   - Link related issues
   - Describe how you tested
   - Include screenshots if relevant

## Commit message conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): subject

body

footer
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, missing semi-colons, etc.
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:

```
feat(proxmox): add support for multiple disk configuration

Add configuration option to specify additional disks for VMs.
This allows separating OS disk from data disk.

Closes #42

---

docs(gpu): clarify extension installation process

Improve explanation of the two approaches for loading GPU extensions
based on feedback from Sidero Labs team.

---

fix(omni): correct SSL certificate path in example

The example pointed to wrong certificate location.
Fixed to use standard Let's Encrypt path.
```

## Code style

### Shell scripts
- Use `#!/bin/bash` shebang
- Enable error checking: `set -euo pipefail`
- Use descriptive variable names
- Quote variables: `"$VARIABLE"`
- Include usage/help functions
- Add error messages for failures

### YAML
- Use 2-space indentation
- Include inline comments for clarity
- Group related settings
- Use meaningful key names

### Markdown
- Use ATX-style headers (`#` not `===`)
- Include code block language specifiers
- Use relative links within repo
- Keep line length reasonable (100-120 chars)

## What we're looking for

### High priority
- Bug fixes and corrections
- Improved error messages
- Additional troubleshooting scenarios
- Real-world usage examples
- Documentation improvements

### Feature ideas
- Alternative authentication providers (beyond Auth0)
- Additional machine class examples
- Monitoring/observability setup
- Backup/restore procedures
- High availability configurations
- Multi-disk VM support (when available in provider)
- Alternative DNS providers (beyond Cloudflare)

### Future considerations
- Terraform modules for infrastructure
- CI/CD pipeline examples
- Cost optimization guides
- Security hardening guides

## Community guidelines

### Be respectful
- Be welcoming to newcomers
- Assume good intentions
- Provide constructive feedback
- Respect different perspectives
- Keep discussions on-topic

### Be helpful
- Answer questions when you can
- Share your experience
- Provide context for decisions
- Link to relevant resources
- Help test PRs and issues

### Be patient
- This is a community project
- Maintainers are volunteers
- Reviews take time
- Not all suggestions will be accepted

## Recognition

Contributors appear in the commit history. Significant contributions are also mentioned in release notes.

## Questions?

Not sure about something?

- Open an issue with the "question" label
- Join [Sidero Labs Slack](https://slack.dev.talos-systems.io/)
- Check existing issues and PRs
- Review the documentation

## License

By contributing, you agree to license your contributions under the project license (see LICENSE file).

## Attribution

This starter kit builds on:
- [Sidero Omni](https://github.com/siderolabs/omni)
- [Talos Linux](https://github.com/siderolabs/talos)
- [Omni Proxmox Provider](https://github.com/siderolabs/omni-infra-provider-proxmox)

Thanks to the Sidero Labs team for their support and tooling.
